from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path, PurePosixPath


HERE = Path(__file__).resolve().parents[1]
BASELINE = HERE / "COMPATIBILITY_BASELINE.json"
OVERRIDES = HERE / "overrides"


class CompatibilityError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_baseline() -> dict[str, object]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def safe_members(archive: zipfile.ZipFile, root: str) -> list[zipfile.ZipInfo]:
    members: list[zipfile.ZipInfo] = []
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] != root:
            raise CompatibilityError(f"unsafe ZIP member: {info.filename!r}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise CompatibilityError(f"symlink ZIP member: {info.filename!r}")
        members.append(info)
    if not members:
        raise CompatibilityError("empty ZIP")
    return members


def extract_safely(archive_path: Path, output: Path, root: str) -> Path:
    if output.exists():
        raise CompatibilityError(f"output already exists: {output}")
    with zipfile.ZipFile(archive_path) as archive:
        members = safe_members(archive, root)
        output.mkdir(parents=True, exist_ok=False)
        for info in members:
            destination = output / PurePosixPath(info.filename)
            if info.is_dir():
                destination.mkdir(parents=True, exist_ok=True)
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            os.chmod(destination, (info.external_attr >> 16) & 0o777 or 0o644)
    return output / root


def parse_manifest(root: Path) -> dict[str, str]:
    manifest = root / "MANIFEST.sha256"
    if not manifest.is_file() or manifest.is_symlink():
        raise CompatibilityError("MANIFEST.sha256 missing or unsafe")
    entries: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        digest, separator, relative = line.partition("  ")
        if not separator or len(digest) != 64 or not relative:
            raise CompatibilityError("invalid manifest line")
        entries[relative] = digest
    return entries


def verify_manifest(root: Path) -> None:
    entries = parse_manifest(root)
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "MANIFEST.sha256"
    }
    if set(entries) != set(actual):
        raise CompatibilityError("base manifest file set mismatch")
    bad = [relative for relative, digest in entries.items() if sha256(actual[relative]) != digest]
    if bad:
        raise CompatibilityError(f"base manifest hash mismatch: {bad[:3]}")


def refresh_manifest(root: Path) -> None:
    paths = sorted(
        path for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "MANIFEST.sha256"
    )
    text = "".join(f"{sha256(path)}  {path.relative_to(root).as_posix()}\n" for path in paths)
    (root / "MANIFEST.sha256").write_text(text, encoding="utf-8")


def copy_overrides(root: Path, baseline: dict[str, object]) -> list[dict[str, str]]:
    targets = baseline["override_targets"]
    if not isinstance(targets, list):
        raise CompatibilityError("override_targets must be a list")
    records: list[dict[str, str]] = []
    for target in targets:
        if not isinstance(target, dict):
            raise CompatibilityError("override target must declare a path and SHA-256")
        relative = target.get("path")
        expected_override_hash = target.get("sha256")
        if not isinstance(relative, str) or not relative.startswith("07_IMPLEMENTATION/apply/"):
            raise CompatibilityError("override target is outside the approved apply surface")
        if not isinstance(expected_override_hash, str) or len(expected_override_hash) != 64:
            raise CompatibilityError("override target SHA-256 is invalid")
        source = OVERRIDES / Path(relative).name
        destination = root / relative
        if not source.is_file() or source.is_symlink() or not destination.is_file() or destination.is_symlink():
            raise CompatibilityError(f"missing or unsafe override target: {relative}")
        if sha256(source) != expected_override_hash:
            raise CompatibilityError(f"override SHA-256 does not match baseline: {relative}")
        before = sha256(destination)
        shutil.copy2(source, destination)
        records.append({"path": relative, "base_sha256": before, "compat_sha256": sha256(destination)})
    return records


def verify_compatible_copy(root: Path) -> dict[str, object]:
    verifier = root / "10_ACCEPTANCE/scripts/verify_taskpack.py"
    completed = subprocess.run(
        [sys.executable, str(verifier), "--root", str(root), "--skip-tests"],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        raise CompatibilityError(f"compatible taskpack verifier failed: {(completed.stderr or completed.stdout)[-2000:]}")
    try:
        report = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise CompatibilityError(f"compatible verifier did not emit JSON: {exc}") from exc
    if report.get("overall") != "PASS" or report.get("taskpack_verdict") != "PASS":
        raise CompatibilityError("compatible taskpack verifier did not pass")
    if not (root / "11_AGENT/EXECUTION_ORDER.md").is_file() or not (root / "09_ROADMAP/TASK_GRAPH.json").is_file():
        raise CompatibilityError("required compatibility execution authority is missing")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a disposable Social Archive v0.0.0.4 compatibility extraction.")
    parser.add_argument("--base-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New parent directory for the disposable compatible extraction.")
    args = parser.parse_args()
    baseline = load_baseline()
    base = baseline["base_taskpack"]
    if not isinstance(base, dict):
        raise CompatibilityError("base_taskpack missing")
    archive = args.base_zip.resolve()
    output = args.output.resolve()
    expected_hash = str(base["sha256"])
    expected_root = str(base["root"])
    if not archive.is_file() or archive.is_symlink():
        raise CompatibilityError("base ZIP must be a regular file")
    if sha256(archive) != expected_hash:
        raise CompatibilityError("base ZIP SHA-256 does not match the frozen v0.0.0.4 baseline")
    root = extract_safely(archive, output, expected_root)
    verify_manifest(root)
    overrides = copy_overrides(root, baseline)
    refresh_manifest(root)
    report = verify_compatible_copy(root)
    provenance = {
        "compatibility_id": baseline["compatibility_id"],
        "base_zip_sha256": expected_hash,
        "base_root": expected_root,
        "overrides": overrides,
        "taskpack_verifier_status": report["overall"],
        "taskpack_check_count": len(report.get("checks") or []),
        "execution_authority": ["11_AGENT/EXECUTION_ORDER.md", "09_ROADMAP/TASK_GRAPH.json"],
    }
    (output / "COMPATIBILITY_PROVENANCE.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(provenance, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CompatibilityError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, ensure_ascii=False))
        raise SystemExit(2)
