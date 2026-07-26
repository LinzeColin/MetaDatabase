#!/usr/bin/env python3
"""Build commit-bound CB-120 source, sparse seed and no-clone client artifacts."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import BinaryIO


EXPECTED_ORIGIN = "git@github.com:LinzeColin/MetaDatabase.git"
EXPECTED_BRANCH = "codex/cyberboss-prestage0"
EXPECTED_CLIENT_SHA256 = (
    "8a26302c98a470e75122fbf01ff1d1a23381ccf5db5f26df9ed5f9e59e5c9ffa"
)
EXPECTED_GH_SHA256 = (
    "83d5c2ccad5498f58bf6368acb1ab32588cf43ab3a4b1c301bf36328b1c8bd60"
)
EXPECTED_GH_URL = (
    "https://github.com/cli/cli/releases/download/v2.96.0/"
    "gh_2.96.0_linux_amd64.tar.gz"
)


class BuildViolation(RuntimeError):
    """The requested artifact build is not the locked CB-120 build."""


def expect(condition: bool, code: str) -> None:
    if not condition:
        raise BuildViolation(code)


def command(
    args: list[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise BuildViolation(
            f"command:{args[0]}:{result.returncode}:{result.stderr.strip()[:200]}"
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
        raise BuildViolation(f"source_archive:{stderr.strip()[:200]}")
    output.chmod(0o644)


def git_blob_oids(repo: Path, commit: str) -> list[str]:
    oids: set[str] = set()
    inventories = (
        (
            command(
                [
                    "git",
                    "ls-tree",
                    "-r",
                    "-z",
                    commit,
                    "--",
                    "CyberBoss",
                    ".github",
                ],
                cwd=repo,
            ),
            False,
        ),
        (command(["git", "ls-tree", "-z", commit], cwd=repo), True),
    )
    for inventory, root_only in inventories:
        for raw in inventory.split("\0"):
            if not raw or "\t" not in raw:
                continue
            metadata, path = raw.split("\t", 1)
            parts = metadata.split()
            if len(parts) != 3 or parts[1] != "blob":
                continue
            if not root_only or "/" not in path:
                oids.add(parts[2])
    expect(bool(oids), "seed_blob_inventory_empty")
    return sorted(oids)


def deterministic_tar(root: Path, archive_root: str, output: Path) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode="w") as tar:
                candidates = [root, *sorted(root.rglob("*"))]
                for candidate in candidates:
                    relative = candidate.relative_to(root)
                    name = (
                        archive_root
                        if relative == Path(".")
                        else f"{archive_root}/{relative.as_posix()}"
                    )
                    info = tar.gettarinfo(str(candidate), arcname=name)
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    info.mtime = 0
                    if info.isfile():
                        with candidate.open("rb") as handle:
                            tar.addfile(info, handle)
                    else:
                        tar.addfile(info)
    output.chmod(0o644)


def create_seed(repo: Path, commit: str, branch: str, output: Path) -> dict[str, int]:
    with tempfile.TemporaryDirectory(prefix="cyberboss-seed-") as raw:
        seed = Path(raw) / "seed.git"
        command(
            [
                "git",
                "clone",
                "--upload-pack=git -c uploadpack.allowFilter=true upload-pack",
                "--bare",
                "--single-branch",
                "--branch",
                branch,
                "--filter=blob:none",
                f"file://{repo}",
                str(seed),
            ]
        )
        expect(
            command(["git", "-C", str(seed), "rev-parse", f"refs/heads/{branch}"])
            == commit,
            "seed_commit",
        )
        oids = git_blob_oids(repo, commit)
        hydrate = subprocess.run(
            ["git", "-C", str(seed), "cat-file", "--batch"],
            input=("\n".join(oids) + "\n").encode(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
        expect(hydrate.returncode == 0, "seed_hydration")
        no_fetch = {**os.environ, "GIT_NO_LAZY_FETCH": "1"}
        for oid in oids:
            result = subprocess.run(
                ["git", "-C", str(seed), "cat-file", "-e", f"{oid}^{{blob}}"],
                env=no_fetch,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            expect(result.returncode == 0, f"seed_blob_missing:{oid}")
        command(
            [
                "git",
                "-C",
                str(seed),
                "config",
                "remote.origin.url",
                f"artifact://LinzeColin/MetaDatabase/{commit}",
            ]
        )
        command(
            ["git", "-C", str(seed), "config", "remote.origin.promisor", "true"]
        )
        command(
            [
                "git",
                "-C",
                str(seed),
                "config",
                "remote.origin.partialclonefilter",
                "blob:none",
            ]
        )
        command(
            ["git", "-C", str(seed), "config", "uploadpack.allowFilter", "true"]
        )
        command(
            [
                "git",
                "-C",
                str(seed),
                "config",
                "uploadpack.allowAnySHA1InWant",
                "true",
            ]
        )
        expect(not (seed / "objects/info/alternates").exists(), "seed_alternates")
        config_text = (seed / "config").read_text(encoding="utf-8")
        expect(str(repo) not in config_text, "seed_local_path")
        expect(str(Path.home()) not in config_text, "seed_home_path")
        deterministic_tar(seed, "metadatabase-seed.git", output)
        return {
            "hydrated_blob_count": len(oids),
            "seed_bytes": output.stat().st_size,
        }


def download(url: str, output: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "CyberBoss-CB120-artifact-builder/1"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        with output.open("wb") as handle:
            shutil.copyfileobj(response, handle, length=1024 * 1024)
    output.chmod(0o644)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--branch", default=EXPECTED_BRANCH)
    parser.add_argument("--private-db-client", type=Path, required=True)
    parser.add_argument("--gh-archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        repo = args.repo.resolve(strict=True)
        client = args.private_db_client.resolve(strict=True)
        output = args.output
        expect(output.is_absolute(), "output_absolute")
        expect(not output.exists(), "output_exists")
        expect(
            re.fullmatch(r"[0-9a-f]{40}", args.commit) is not None,
            "commit_format",
        )
        expect(args.branch == EXPECTED_BRANCH, "branch")
        expect(command(["git", "rev-parse", "HEAD"], cwd=repo) == args.commit, "head")
        expect(
            command(["git", "branch", "--show-current"], cwd=repo) == args.branch,
            "current_branch",
        )
        expect(
            command(["git", "remote", "get-url", "origin"], cwd=repo)
            == EXPECTED_ORIGIN,
            "origin",
        )
        expect(command(["git", "status", "--porcelain=v1"], cwd=repo) == "", "dirty")
        expect(client.name == "private_db_client.py", "client_name")
        expect(sha256(client) == EXPECTED_CLIENT_SHA256, "client_hash")

        output.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(
            tempfile.mkdtemp(prefix=".cb120-artifacts-", dir=output.parent)
        )
        try:
            source_name = f"cyberboss-source-{args.commit}.tar.gz"
            seed_name = f"metadatabase-seed-{args.commit}.git.tar.gz"
            client_name = "private_db_client.py"
            gh_name = "gh_2.96.0_linux_amd64.tar.gz"
            source_path = stage / source_name
            seed_path = stage / seed_name
            client_path = stage / client_name
            gh_path = stage / gh_name

            create_source_archive(repo, args.commit, source_path)
            seed_facts = create_seed(
                repo, args.commit, args.branch, seed_path
            )
            shutil.copyfile(client, client_path)
            client_path.chmod(0o644)
            if args.gh_archive:
                supplied = args.gh_archive.resolve(strict=True)
                expect(sha256(supplied) == EXPECTED_GH_SHA256, "gh_supplied_hash")
                shutil.copyfile(supplied, gh_path)
                gh_path.chmod(0o644)
            else:
                download(EXPECTED_GH_URL, gh_path)
            expect(sha256(gh_path) == EXPECTED_GH_SHA256, "gh_download_hash")

            manifest = {
                "schema_version": 1,
                "task_id": "CB-120",
                "release_commit": args.commit,
                "branch": args.branch,
                "repository": "LinzeColin/MetaDatabase",
                "repository_tree": command(
                    ["git", "rev-parse", f"{args.commit}^{{tree}}"], cwd=repo
                ),
                "cyberboss_tree": command(
                    ["git", "rev-parse", f"{args.commit}:CyberBoss"], cwd=repo
                ),
                "source": {
                    "archive": source_name,
                    "sha256": sha256(source_path),
                    "corresponding_source_complete": True,
                    "license_expression":
                    "AGPL-3.0-only AND GPL-3.0-only",
                    "original_licenses_preserved": True,
                    "conflict_record":
                    "docs/evidence/CB-000/LICENSE_COMPLIANCE.md",
                    "post_baseline_modification_record":
                    "machine/facts/post-baseline-change-ledger.json",
                    "upstream_clarification_received": False,
                },
                "workspace_seed": {
                    "archive": seed_name,
                    "sha256": sha256(seed_path),
                    "filter": "blob:none",
                    "sparse_paths": ["CyberBoss", ".github"],
                    "root_integration_write": False,
                    **seed_facts,
                },
                "private_db_client": {
                    "file": client_name,
                    "sha256": sha256(client_path),
                    "repository": "LinzeColin/KMOS",
                    "source_path":
                    "KMDatabase/machine/tools/private_db_client.py",
                    "access_mode": "no_clone_client",
                    "allowed_operations": ["ingest", "get", "list", "verify"],
                    "real_operation_activation": "activation_pending",
                },
                "github_cli": {
                    "file": gh_name,
                    "version": "2.96.0",
                    "sha256": sha256(gh_path),
                    "url": EXPECTED_GH_URL,
                    "license": "MIT",
                },
                "deployment": {
                    "switch_current": False,
                    "enable_service": False,
                    "start_business_runtime": False,
                    "clone_private_database": False,
                    "remote_publication": "none",
                },
            }
            manifest_path = stage / "artifact-manifest.json"
            write_json(manifest_path, manifest)
            checked = [source_path, seed_path, client_path, gh_path, manifest_path]
            checksums = "".join(
                f"{sha256(path)}  {path.name}\n"
                for path in sorted(checked, key=lambda item: item.name)
            )
            (stage / "SHA256SUMS").write_text(checksums, encoding="ascii")
            (stage / "SHA256SUMS").chmod(0o644)
            os.replace(stage, output)
        except BaseException:
            shutil.rmtree(stage, ignore_errors=True)
            raise
    except (
        BuildViolation,
        OSError,
        subprocess.SubprocessError,
        urllib.error.URLError,
    ) as error:
        print(f"CB120_ARTIFACT_BUILD=FAIL reason={error}")
        return 2

    print(
        "CB120_ARTIFACT_BUILD=PASS "
        f"release_commit={args.commit} "
        f"output_files={len(list(output.iterdir()))} "
        "filter=blob:none sparse=CyberBoss,.github "
        "private_database_clone=false publication=none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
