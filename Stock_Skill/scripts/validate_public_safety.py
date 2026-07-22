#!/usr/bin/env python3
"""Fail closed when public Stock Skill surfaces contain private material."""

from __future__ import annotations

import argparse
import re
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile, ZipFile


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ZIP_ENTRY_BYTES = 16 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 64 * 1024 * 1024
EXACT_HISTORICAL_PATH = b"/home/" + b"oai/" + b"skills"
SAFE_HISTORICAL_PATH_BOUNDARIES = frozenset(
    ".,;:!?)]}。．，、；：！？）］｝》】」』"
)
USER_PATH_SEGMENT = rb"""(?P<user>[^\x00-\x20\x7f/\\`"'<>(){}\[\]]+)"""
POSIX_USER_PATH_END = rb"""(?:/|(?=[\x00-\x20\x7f`"'<>(){}\[\]]|$))"""
WINDOWS_USER_PATH_END = (
    rb"""(?:(?:\\|/)|(?=[\x00-\x20\x7f`"'<>(){}\[\]]|$))"""
)
USER_PATH_PATTERN_NAMES = {
    "macOS user path",
    "Linux user path",
    "Windows user path",
}
PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    "AWS access key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "GitHub stateless App token": re.compile(
        rb"\bghs_[0-9]+_[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
        rb"(?![A-Za-z0-9_-])"
    ),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "GitHub fine-grained PAT": re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    "OpenAI-style secret": re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
    "Bearer token": re.compile(rb"\bBearer[ \t]+[A-Za-z0-9._~-]{20,}\b"),
    "macOS user path": re.compile(
        rb"(?:file://)?/users/" + USER_PATH_SEGMENT + POSIX_USER_PATH_END,
        flags=re.IGNORECASE,
    ),
    "Linux user path": re.compile(
        rb"(?:file://)?/home/" + USER_PATH_SEGMENT + POSIX_USER_PATH_END
    ),
    "Windows user path": re.compile(
        rb"[a-z]:(?:\\|/)users(?:\\|/)"
        + USER_PATH_SEGMENT
        + WINDOWS_USER_PATH_END,
        flags=re.IGNORECASE,
    ),
}


@dataclass
class ScanState:
    errors: list[str] = field(default_factory=list)
    scanned_blobs: int = 0
    scanned_zip_entries: int = 0


def first_utf8_character(raw: bytes) -> str | None:
    for width in range(1, min(4, len(raw)) + 1):
        try:
            decoded = raw[:width].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if len(decoded) == 1:
            return decoded
    return None


def is_safe_historical_path_right_boundary(data: bytes, closing_tick: int) -> bool:
    trailing = data[closing_tick + 1 :]
    if not trailing:
        return True
    character = first_utf8_character(trailing)
    return character is not None and (
        character.isspace() or character in SAFE_HISTORICAL_PATH_BOUNDARIES
    )


def is_exact_historical_linux_path(data: bytes, match: re.Match[bytes]) -> bool:
    if not match.group(0).startswith(b"/home/"):
        return False
    home_start = data.find(b"/home/", match.start(), match.end())
    if home_start < 0 or not data.startswith(EXACT_HISTORICAL_PATH, home_start):
        return False
    end = home_start + len(EXACT_HISTORICAL_PATH)
    return (
        home_start > 0
        and data[home_start - 1 : home_start] == b"`"
        and data[end : end + 1] == b"`"
        and is_safe_historical_path_right_boundary(data, end)
    )


def is_documentation_user_placeholder(match: re.Match[bytes]) -> bool:
    try:
        user = match.group("user").decode("utf-8")
    except (IndexError, UnicodeDecodeError):
        return False
    return bool(user) and all(character in {".", "…"} for character in user)


def scan_blob(label: str, data: bytes, state: ScanState) -> None:
    state.scanned_blobs += 1
    for pattern_name, pattern in PATTERNS.items():
        for match in pattern.finditer(data):
            if (
                pattern_name in USER_PATH_PATTERN_NAMES
                and is_documentation_user_placeholder(match)
            ):
                continue
            if (
                pattern_name == "Linux user path"
                and is_exact_historical_linux_path(data, match)
            ):
                continue
            state.errors.append(f"{label}: forbidden {pattern_name}")


def safe_zip_name(raw: str, is_directory: bool) -> bool:
    posix = PurePosixPath(raw)
    canonical = posix.as_posix() + ("/" if is_directory else "")
    return (
        bool(raw)
        and not posix.is_absolute()
        and "\\" not in raw
        and re.match(r"^[A-Za-z]:", raw) is None
        and raw == canonical
        and all(part not in {"", ".", ".."} for part in posix.parts)
    )


def relative_label(repo_root: Path, path: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def scan_public_surfaces(repo_root: Path) -> tuple[int, int, int, list[str]]:
    state = ScanState()
    stock_root = repo_root / "Stock_Skill"
    scope = [repo_root / "AGENTS.md", repo_root / "README.md"]
    if stock_root.is_symlink() or not stock_root.is_dir():
        state.errors.append("Stock_Skill: root must be a non-symlink directory")
    else:
        scope.extend(sorted(stock_root.rglob("*"), key=lambda path: path.as_posix()))

    files: list[Path] = []
    for path in scope:
        label = relative_label(repo_root, path)
        if not path.exists() and not path.is_symlink():
            state.errors.append(f"{label}: required public surface is missing")
            continue
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            if not path.is_dir():
                state.errors.append(f"{label}: tracked cache file is prohibited")
            continue
        if path.name == ".DS_Store":
            state.errors.append(f"{label}: tracked OS metadata is prohibited")
            continue
        if path.is_symlink() or not path.is_dir():
            files.append(path)

    if not files:
        state.errors.append("public-safety scan found no files")
    for path in files:
        label = relative_label(repo_root, path)
        try:
            metadata = path.lstat()
        except OSError as exc:
            state.errors.append(f"{label}: cannot stat file: {exc}")
            continue
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            state.errors.append(f"{label}: non-regular or symlink path")
            continue
        if metadata.st_size > MAX_FILE_BYTES:
            state.errors.append(f"{label}: file exceeds {MAX_FILE_BYTES} byte scan limit")
            continue
        try:
            data = path.read_bytes()
        except OSError as exc:
            state.errors.append(f"{label}: cannot read file: {exc}")
            continue
        scan_blob(label, data, state)
        if path.suffix.lower() != ".zip":
            continue
        try:
            with ZipFile(path) as archive:
                seen: set[str] = set()
                total = 0
                for info in archive.infolist():
                    zip_label = f"{label}!{info.filename}"
                    if not safe_zip_name(info.filename, info.is_dir()):
                        state.errors.append(f"{zip_label}: unsafe ZIP path")
                        continue
                    if info.filename in seen:
                        state.errors.append(f"{zip_label}: duplicate ZIP entry")
                        continue
                    seen.add(info.filename)
                    mode = info.external_attr >> 16
                    if stat.S_ISLNK(mode):
                        state.errors.append(f"{zip_label}: symlink ZIP entry")
                        continue
                    if info.flag_bits & 0x1:
                        state.errors.append(f"{zip_label}: encrypted ZIP entry")
                        continue
                    file_type = stat.S_IFMT(mode)
                    if info.is_dir():
                        if file_type not in {0, stat.S_IFDIR}:
                            state.errors.append(
                                f"{zip_label}: non-directory mode on directory entry"
                            )
                    elif file_type not in {0, stat.S_IFREG}:
                        state.errors.append(f"{zip_label}: non-regular ZIP entry")
                        continue
                    total += info.file_size
                    if info.file_size > MAX_ZIP_ENTRY_BYTES:
                        state.errors.append(
                            f"{zip_label}: entry exceeds {MAX_ZIP_ENTRY_BYTES} byte limit"
                        )
                        continue
                    if total > MAX_ZIP_TOTAL_BYTES:
                        state.errors.append(
                            f"{label}: archive exceeds {MAX_ZIP_TOTAL_BYTES} uncompressed bytes"
                        )
                        break
                    if info.is_dir():
                        if info.file_size != 0:
                            state.errors.append(
                                f"{zip_label}: non-empty directory ZIP entry"
                            )
                        continue
                    scan_blob(zip_label, archive.read(info), state)
                    state.scanned_zip_entries += 1
        except (BadZipFile, OSError, RuntimeError) as exc:
            state.errors.append(f"{label}: unreadable ZIP: {exc}")

    return len(files), state.scanned_blobs, state.scanned_zip_entries, state.errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def main() -> int:
    try:
        repo_root = parse_args().repo_root.resolve(strict=True)
        files, blobs, zip_entries, errors = scan_public_surfaces(repo_root)
    except OSError as exc:
        print(f"FAIL: invalid repository root: {exc}", file=sys.stderr)
        return 1
    if errors:
        print(f"FAIL: public-safety scan ({len(errors)} error(s))", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(
        f"PASS: public-safety scanned {files} files, {blobs} blobs, "
        f"and {zip_entries} ZIP entries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
