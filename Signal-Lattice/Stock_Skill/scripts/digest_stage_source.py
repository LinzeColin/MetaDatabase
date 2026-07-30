#!/usr/bin/env python3
"""Compute a fail-closed digest of every proposed Stage change against HEAD."""

from __future__ import annotations

import argparse
import hashlib
import stat
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePosixPath


class DigestError(RuntimeError):
    """Raised when the Stage subject cannot be represented unambiguously."""


def run_git(repo_root: Path, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise DigestError(
            f"git {' '.join(arguments)} failed with {result.returncode}: {detail}"
        )
    return result


def resolve_repo_root(raw_root: Path) -> Path:
    if raw_root.is_symlink():
        raise DigestError("repository root must not be a symlink")
    try:
        requested = raw_root.resolve(strict=True)
    except OSError as exc:
        raise DigestError(f"repository root is unavailable: {exc}") from exc
    if not requested.is_dir():
        raise DigestError("repository root must be a directory")
    top_level = run_git(requested, "rev-parse", "--show-toplevel").stdout
    try:
        discovered = Path(top_level.decode("utf-8").strip()).resolve(strict=True)
    except (OSError, UnicodeDecodeError) as exc:
        raise DigestError(f"cannot resolve Git top-level: {exc}") from exc
    if requested != discovered:
        raise DigestError(
            f"repository root must equal Git top-level: {requested} != {discovered}"
        )
    return requested


def split_git_paths(raw: bytes, source: str) -> list[str]:
    if not raw:
        return []
    if not raw.endswith(b"\0"):
        raise DigestError(f"{source} did not return NUL-terminated paths")
    paths: list[str] = []
    for encoded in raw[:-1].split(b"\0"):
        try:
            relative = encoded.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DigestError(f"{source} returned a non-UTF-8 path") from exc
        if relative != unicodedata.normalize("NFC", relative):
            raise DigestError(f"non-NFC Stage path: {relative!r}")
        posix = PurePosixPath(relative)
        if (
            not relative
            or relative.startswith("/")
            or relative != posix.as_posix()
            or any(part in {"", ".", ".."} for part in posix.parts)
        ):
            raise DigestError(f"unsafe or non-canonical Stage path: {relative!r}")
        paths.append(relative)
    return paths


def collect_subject(repo_root: Path) -> tuple[str, list[tuple[bytes, ...]]]:
    # Git hides intent-to-add entries from a cached diff unless this option is set.
    index = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--quiet",
            "--exit-code",
            "--ita-visible-in-index",
            "HEAD",
            "--",
        ],
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if index.returncode == 1:
        raise DigestError("Git index must be empty relative to HEAD during Review")
    if index.returncode != 0:
        detail = index.stderr.decode("utf-8", errors="replace").strip()
        raise DigestError(f"cannot verify Git index: {detail}")
    if run_git(repo_root, "ls-files", "--unmerged", "-z").stdout:
        raise DigestError("unmerged index entries are prohibited")

    base = run_git(repo_root, "rev-parse", "--verify", "HEAD^{commit}").stdout
    try:
        base_oid = base.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise DigestError("HEAD object ID is not ASCII") from exc
    if not base_oid or any(character not in "0123456789abcdef" for character in base_oid):
        raise DigestError(f"invalid HEAD object ID: {base_oid!r}")

    tracked = run_git(
        repo_root,
        "-c",
        "core.fileMode=true",
        "diff",
        "--no-ext-diff",
        "--no-renames",
        "--name-only",
        "-z",
        "HEAD",
        "--",
    ).stdout
    untracked = run_git(
        repo_root, "ls-files", "--others", "--exclude-standard", "-z", "--"
    ).stdout
    relative_paths = split_git_paths(tracked, "git diff") + split_git_paths(
        untracked, "git ls-files"
    )
    if len(relative_paths) != len(set(relative_paths)):
        raise DigestError("duplicate Stage path after tracked/untracked union")
    if not relative_paths:
        raise DigestError("Stage source subject is empty")

    records: list[tuple[bytes, ...]] = []
    for relative in relative_paths:
        encoded = relative.encode("utf-8")
        target = repo_root.joinpath(*PurePosixPath(relative).parts)
        if target.is_symlink():
            raise DigestError(f"Stage symlink is prohibited: {relative}")
        if target.exists():
            metadata = target.lstat()
            if not stat.S_ISREG(metadata.st_mode):
                raise DigestError(f"Stage path is not a regular file: {relative}")
            try:
                target.resolve(strict=True).relative_to(repo_root)
            except (OSError, ValueError) as exc:
                raise DigestError(f"Stage path escapes repository: {relative}") from exc
            # Git canonicalizes executable mode from the owner execute bit only.
            git_mode = b"100755" if metadata.st_mode & stat.S_IXUSR else b"100644"
            records.append((b"F", encoded, git_mode, target.read_bytes()))
            continue

        object_type = run_git(repo_root, "cat-file", "-t", f"{base_oid}:{relative}")
        if object_type.stdout.strip() != b"blob":
            raise DigestError(f"deleted Stage path is not a base blob: {relative}")
        records.append((b"D", encoded))

    records.sort(key=lambda record: record[1])
    return base_oid, records


def digest_subject(base_oid: str, records: list[tuple[bytes, ...]]) -> str:
    value = hashlib.sha256()
    value.update(b"BASE\0")
    value.update(base_oid.encode("ascii"))
    value.update(b"\0")
    for record in records:
        kind, relative, *payload = record
        value.update(kind)
        value.update(b"\0")
        value.update(relative)
        value.update(b"\0")
        for part in payload:
            value.update(part)
            value.update(b"\0")
    return value.hexdigest()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Git top-level to inspect (default: current directory)",
    )
    return parser.parse_args()


def main() -> int:
    try:
        repo_root = resolve_repo_root(parse_args().repo_root)
        base_oid, records = collect_subject(repo_root)
        subject_digest = digest_subject(base_oid, records)
    except (DigestError, OSError) as exc:
        print(f"FAIL: cannot digest Stage source: {exc}", file=sys.stderr)
        return 1
    print(f"BASE_HEAD={base_oid}")
    print(f"SUBJECT_PATHS={len(records)}")
    print(f"STAGE_SOURCE_SHA256={subject_digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
