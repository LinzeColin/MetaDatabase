from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

EXCLUDED_NAMES = {".coverage", ".DS_Store"}
EXCLUDED_PARTS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".swp", ".tmp"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".yaml", ".yml", ".sh", ".txt"}
UNRESOLVED_TERMS = ("TO" + "DO", "T" + "BD", "FIX" + "ME")
UNRESOLVED_PATTERN = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(UNRESOLVED_TERMS) + r")(?![A-Za-z0-9_])")
FORBIDDEN_ARCHIVE_PATTERN = re.compile(r"(^|/)(\.\.?)(/|$)")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MANIFEST_SCHEMA = "efs.internal_snapshot_manifest.v2"
MAX_ENTRIES = 4096
MAX_FILE_BYTES = 20_000_000
MAX_TOTAL_BYTES = 100_000_000
MAX_MANIFEST_BYTES = 5_000_000
MAX_ARCHIVE_BYTES = 120_000_000
MAX_COMPRESSION_RATIO = 200


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalized_rel(path: Path, root: Path) -> str:
    raw = path.relative_to(root).as_posix()
    value = unicodedata.normalize("NFC", raw)
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or not value or FORBIDDEN_ARCHIVE_PATTERN.search(value):
        raise ValueError(f"unsafe relative path: {raw}")
    return value


def collect(root: Path) -> list[tuple[str, Path, bytes]]:
    entries: list[tuple[str, Path, bytes]] = []
    seen_exact: set[str] = set()
    seen_folded: set[str] = set()
    total = 0
    for path in sorted(root.rglob("*"), key=lambda item: unicodedata.normalize("NFC", item.as_posix())):
        if path.is_symlink():
            raise ValueError(f"symlink forbidden: {path}")
        if path.is_dir():
            continue
        rel = normalized_rel(path, root)
        if path.name in EXCLUDED_NAMES or any(part in EXCLUDED_PARTS for part in Path(rel).parts) or path.suffix in EXCLUDED_SUFFIXES:
            continue
        folded = rel.casefold()
        if rel in seen_exact or folded in seen_folded:
            raise ValueError(f"duplicate/case-colliding path: {rel}")
        if len(entries) >= MAX_ENTRIES:
            raise ValueError("snapshot file count exceeds limit")
        seen_exact.add(rel)
        seen_folded.add(folded)
        data = path.read_bytes()
        if len(data) > MAX_FILE_BYTES:
            raise ValueError(f"file exceeds snapshot byte limit: {rel}")
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            raise ValueError("snapshot total bytes exceed limit")
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = data.decode("utf-8", errors="strict")
            if UNRESOLVED_PATTERN.search(text):
                raise ValueError(f"unresolved marker in {rel}")
        entries.append((rel, path, data))
    if not entries:
        raise ValueError("snapshot has no files")
    return entries


def build_manifest(entries: list[tuple[str, Path, bytes]], subject: str) -> dict:
    if not isinstance(subject, str) or not subject or len(subject.encode("utf-8")) > 512:
        raise ValueError("snapshot subject must be bounded and non-empty")
    files = [
        {"path": rel, "size": len(data), "sha256": sha256_bytes(data)}
        for rel, _path, data in entries
    ]
    return {
        "schema": MANIFEST_SCHEMA,
        "subject": subject,
        "file_count": len(files),
        "total_bytes": sum(item["size"] for item in files),
        "files": files,
    }


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.create_system = 3
    return info


def seal(root: Path, output: Path, subject: str) -> dict:
    root = root.resolve()
    entries = collect(root)
    manifest = build_manifest(entries, subject)
    manifest_bytes = canonical_json(manifest)
    if len(manifest_bytes) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds byte limit")
    manifest_sha = sha256_bytes(manifest_bytes)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
        tmp = Path(handle.name)
    try:
        with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for rel, _path, data in entries:
                archive.writestr(zip_info(f"payload/{rel}"), data)
            archive.writestr(zip_info("MANIFEST.json"), manifest_bytes)
            archive.writestr(zip_info("MANIFEST.sha256"), (manifest_sha + "  MANIFEST.json\n").encode("ascii"))
        if tmp.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("archive exceeds byte limit")
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)
    report = verify(output)
    report["subject"] = subject
    return report


def _safe_info(info: zipfile.ZipInfo) -> None:
    name = info.filename
    normalized = unicodedata.normalize("NFC", name)
    if normalized != name:
        raise ValueError(f"noncanonical archive path: {name}")
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or FORBIDDEN_ARCHIVE_PATTERN.search(name):
        raise ValueError(f"unsafe archive path: {name}")
    if info.flag_bits & 0x1:
        raise ValueError(f"encrypted archive member forbidden: {name}")
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode) or (mode and not stat.S_ISREG(mode)):
        raise ValueError(f"non-regular archive member forbidden: {name}")
    if info.file_size > MAX_FILE_BYTES:
        raise ValueError(f"archive member exceeds byte limit: {name}")
    if info.file_size and info.compress_size == 0:
        raise ValueError(f"invalid compressed size: {name}")
    if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
        raise ValueError(f"archive compression ratio exceeds limit: {name}")


def _validate_manifest(manifest: object) -> dict:
    if not isinstance(manifest, dict) or set(manifest) != {"schema", "subject", "file_count", "total_bytes", "files"}:
        raise ValueError("manifest shape mismatch")
    if manifest["schema"] != MANIFEST_SCHEMA:
        raise ValueError("manifest schema mismatch")
    if not isinstance(manifest["subject"], str) or not manifest["subject"] or len(manifest["subject"].encode("utf-8")) > 512:
        raise ValueError("manifest subject invalid")
    files = manifest["files"]
    if not isinstance(files, list) or len(files) > MAX_ENTRIES:
        raise ValueError("manifest files invalid")
    if manifest["file_count"] != len(files):
        raise ValueError("manifest file count mismatch")
    paths = []
    total = 0
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "size", "sha256"}:
            raise ValueError("manifest file entry invalid")
        path = item["path"]
        if not isinstance(path, str) or not path or path != unicodedata.normalize("NFC", path):
            raise ValueError("manifest path invalid")
        pure = PurePosixPath(path)
        if pure.is_absolute() or ".." in pure.parts or FORBIDDEN_ARCHIVE_PATTERN.search(path):
            raise ValueError("manifest path unsafe")
        size = item["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0 or size > MAX_FILE_BYTES:
            raise ValueError("manifest size invalid")
        if not isinstance(item["sha256"], str) or not SHA256_PATTERN.fullmatch(item["sha256"]):
            raise ValueError("manifest SHA-256 invalid")
        total += size
        paths.append(path)
    if paths != sorted(paths) or len(paths) != len(set(paths)) or len({path.casefold() for path in paths}) != len(paths):
        raise ValueError("manifest paths are unsorted, duplicated, or case-colliding")
    if total != manifest["total_bytes"] or total > MAX_TOTAL_BYTES:
        raise ValueError("manifest total bytes mismatch")
    return manifest


def verify(path: Path) -> dict:
    if path.is_symlink() or not path.is_file():
        raise ValueError("archive path must be a regular file")
    archive_size = path.stat().st_size
    if archive_size > MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds byte limit")
    data = path.read_bytes()
    seen: set[str] = set()
    with zipfile.ZipFile(path, "r") as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES + 2:
            raise ValueError("archive entry count exceeds limit")
        total_uncompressed = 0
        for info in infos:
            name = info.filename
            if name.casefold() in seen:
                raise ValueError(f"duplicate archive path: {name}")
            seen.add(name.casefold())
            _safe_info(info)
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_TOTAL_BYTES + MAX_MANIFEST_BYTES + 1024:
                raise ValueError("archive total uncompressed bytes exceed limit")
        names = [info.filename for info in infos]
        required = {"MANIFEST.json", "MANIFEST.sha256"}
        if not required.issubset(names):
            raise ValueError("archive lacks manifest files")
        manifest_info = archive.getinfo("MANIFEST.json")
        if manifest_info.file_size > MAX_MANIFEST_BYTES:
            raise ValueError("manifest exceeds byte limit")
        manifest_bytes = archive.read("MANIFEST.json")
        digest_text = archive.read("MANIFEST.sha256").decode("ascii", errors="strict")
        parts = digest_text.split()
        if len(parts) != 2 or parts[1] != "MANIFEST.json" or not SHA256_PATTERN.fullmatch(parts[0]):
            raise ValueError("manifest digest record invalid")
        claimed = parts[0]
        if sha256_bytes(manifest_bytes) != claimed:
            raise ValueError("manifest digest mismatch")
        manifest = _validate_manifest(json.loads(manifest_bytes.decode("utf-8", errors="strict")))
        for item in manifest["files"]:
            member = "payload/" + item["path"]
            payload = archive.read(member)
            if len(payload) != item["size"] or sha256_bytes(payload) != item["sha256"]:
                raise ValueError(f"payload mismatch: {item['path']}")
        expected_names = required | {"payload/" + item["path"] for item in manifest["files"]}
        if set(names) != expected_names or len(names) != len(expected_names):
            raise ValueError("archive contains unmanifested, duplicate, or missing files")
    return {
        "schema": "efs.internal_snapshot_verification.v2",
        "zip_path": path.name,
        "zip_size": len(data),
        "zip_sha256": sha256_bytes(data),
        "manifest_sha256": claimed,
        "file_count": manifest["file_count"],
        "total_payload_bytes": manifest["total_bytes"],
        "status": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("root", type=Path)
    create.add_argument("output", type=Path)
    create.add_argument("--subject", required=True)
    check = sub.add_parser("verify")
    check.add_argument("zip", type=Path)
    args = parser.parse_args()
    result = seal(args.root, args.output, args.subject) if args.command == "create" else verify(args.zip)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
