#!/usr/bin/env python3
"""Build, activate, and verify the deterministic v0.0.0.1 release."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath


STABLE_ID = "bottleneck-serenity-skill"
VERSION = "0.0.0.1"
VERSION_SCHEME = "numeric-quad"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
TASK_PACK = PROJECT_ROOT / "task-pack"
TASK_MANIFEST = TASK_PACK / "MANIFEST.sha256"
BACKUP_MANIFEST = PROJECT_ROOT / "BACKUP_MANIFEST.sha256"
REGISTRY = REPO_ROOT / "Stock_Skill" / "REGISTRY.json"
RELEASE_FILENAME = (
    "bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip"
)
RELEASE_RELATIVE = PurePosixPath("releases") / RELEASE_FILENAME
RELEASE_PATH = PROJECT_ROOT.joinpath(*RELEASE_RELATIVE.parts)
SUMS_PATH = PROJECT_ROOT / "releases" / "SHA256SUMS"
ZIP_ROOT = "bottleneck-serenity-skill-task-pack-v0.0.0.1"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
ACTIVATION_DATE = "2026-07-23"
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  \./(.+)")
SHA256 = re.compile(r"[0-9a-f]{64}")
NUMERIC_QUAD = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
)
EXPECTED_EXECUTABLES = {
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/analyze_portfolio_clusters.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/new_research_case.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/score_opportunity.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_evidence.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_forward_test.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_historical_e2e.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_skill.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_security_evals.py"
    ),
    PurePosixPath(
        "skill_draft/bottleneck-serenity-skill/scripts/validate_trigger_evals.py"
    ),
}
CLAIM_PATHS = [
    "AGENTS.md",
    "README.md",
    "Stock_Skill/AGENTS.md",
    "Stock_Skill/README.md",
    "Stock_Skill/bottleneck-serenity-skill/AGENTS.md",
    "Stock_Skill/bottleneck-serenity-skill/README.md",
]
CLAIM_MARKER = f"{STABLE_ID}={VERSION}"
STALE_DISCOVERY_MARKERS = (
    "REGISTRY_NOT_ACTIVE",
    "RELEASE_NOT_BUILT",
    "尚未登记",
    "待激活项目",
    "待激活版本合同",
    "规划中、未登记",
)


class ReleaseError(RuntimeError):
    """A deterministic release or activation invariant failed."""


def digest_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def digest_path(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def canonical_relative(raw: str, label: str) -> PurePosixPath:
    if not raw or raw != unicodedata.normalize("NFC", raw):
        raise ReleaseError(f"{label}: empty or non-NFC path")
    if "\\" in raw or "\x00" in raw or re.match(r"^[A-Za-z]:", raw):
        raise ReleaseError(f"{label}: non-POSIX path {raw!r}")
    posix = PurePosixPath(raw)
    if (
        posix.is_absolute()
        or raw != posix.as_posix()
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise ReleaseError(f"{label}: unsafe or non-canonical path {raw!r}")
    return posix


def regular_file(path: Path, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ReleaseError(f"{label}: missing file {path}") from exc
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise ReleaseError(f"{label}: must be a regular non-symlink file")


def safe_target(base: Path, relative: PurePosixPath, label: str) -> Path:
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ReleaseError(f"{label}: symlink path component {current}")
    try:
        current.resolve().relative_to(base.resolve())
    except (OSError, ValueError) as exc:
        raise ReleaseError(f"{label}: path escapes root") from exc
    return current


def validate_versions() -> None:
    if not NUMERIC_QUAD.fullmatch(VERSION):
        raise ReleaseError("configured release version is not canonical numeric-quad")
    for path in (PROJECT_ROOT / "VERSION", TASK_PACK / "VERSION"):
        regular_file(path, "VERSION")
        if path.read_bytes() != f"{VERSION}\n".encode("utf-8"):
            raise ReleaseError(f"{path}: must contain exactly {VERSION!r} plus newline")


def collect_files(base: Path, excluded: set[Path]) -> dict[PurePosixPath, Path]:
    files: dict[PurePosixPath, Path] = {}
    for path in base.rglob("*"):
        relative = PurePosixPath(path.relative_to(base).as_posix())
        if "__pycache__" in relative.parts or path.suffix in {".pyc", ".pyo"}:
            raise ReleaseError(f"cache artifact is prohibited: {relative.as_posix()}")
        mode = path.lstat().st_mode
        if path.is_symlink():
            raise ReleaseError(f"symlink is prohibited: {relative.as_posix()}")
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ReleaseError(f"non-regular file is prohibited: {relative.as_posix()}")
        if path in excluded:
            continue
        canonical_relative(relative.as_posix(), "filesystem entry")
        files[relative] = path
    return files


def parse_manifest(
    manifest: Path,
    base: Path,
    *,
    excluded: set[Path],
) -> dict[PurePosixPath, str]:
    regular_file(manifest, "manifest")
    payload = manifest.read_text(encoding="utf-8")
    if not payload or not payload.endswith("\n"):
        raise ReleaseError(f"{manifest}: manifest must be non-empty and newline-terminated")
    declared: dict[PurePosixPath, str] = {}
    raw_order: list[str] = []
    for number, line in enumerate(payload.splitlines(), 1):
        match = MANIFEST_LINE.fullmatch(line)
        if not match:
            raise ReleaseError(f"{manifest}:{number}: invalid manifest line")
        relative = canonical_relative(match.group(2), f"{manifest}:{number}")
        if relative in declared:
            raise ReleaseError(f"{manifest}:{number}: duplicate path {relative}")
        target = safe_target(base, relative, f"{manifest}:{number}")
        regular_file(target, f"{manifest}:{number}")
        observed = digest_path(target)
        if observed != match.group(1):
            raise ReleaseError(
                f"{manifest}:{number}: SHA-256 mismatch for {relative}: "
                f"expected {match.group(1)}, got {observed}"
            )
        declared[relative] = match.group(1)
        raw_order.append(relative.as_posix())
    if raw_order != sorted(raw_order, key=lambda value: value.encode("utf-8")):
        raise ReleaseError(f"{manifest}: entries are not in UTF-8 byte order")
    actual = collect_files(base, excluded)
    if set(declared) != set(actual):
        missing = sorted(
            (path.as_posix() for path in set(actual) - set(declared)),
            key=lambda value: value.encode("utf-8"),
        )
        stale = sorted(
            (path.as_posix() for path in set(declared) - set(actual)),
            key=lambda value: value.encode("utf-8"),
        )
        raise ReleaseError(f"{manifest}: file-set mismatch; unlisted={missing}; stale={stale}")
    return declared


def validate_task_manifest() -> list[PurePosixPath]:
    declared = parse_manifest(
        TASK_MANIFEST,
        TASK_PACK,
        excluded={TASK_MANIFEST},
    )
    executable = {
        relative
        for relative in declared
        if TASK_PACK.joinpath(*relative.parts).stat().st_mode & stat.S_IXUSR
    }
    if executable != EXPECTED_EXECUTABLES:
        raise ReleaseError(
            "task-pack executable set mismatch: "
            f"expected={sorted(map(str, EXPECTED_EXECUTABLES))}; "
            f"observed={sorted(map(str, executable))}"
        )
    return sorted(
        [*declared, PurePosixPath("MANIFEST.sha256")],
        key=lambda path: path.as_posix().encode("utf-8"),
    )


def expected_zip_entries(
    files: list[PurePosixPath],
) -> list[tuple[str, PurePosixPath | None]]:
    entries: dict[str, PurePosixPath | None] = {f"{ZIP_ROOT}/": None}
    for relative in files:
        parts = relative.parts
        for length in range(1, len(parts)):
            directory = "/".join((ZIP_ROOT, *parts[:length])) + "/"
            entries[directory] = None
        name = "/".join((ZIP_ROOT, *parts))
        entries[name] = relative
    return sorted(entries.items(), key=lambda item: item[0].encode("utf-8"))


def zip_info(name: str, *, is_directory: bool, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
    info.create_system = 3
    info.compress_type = zipfile.ZIP_STORED
    info.comment = b""
    info.extra = b""
    info.internal_attr = 0
    file_type = stat.S_IFDIR if is_directory else stat.S_IFREG
    info.external_attr = (file_type | mode) << 16
    if is_directory:
        info.external_attr |= 0x10
    return info


def render_release(destination: Path, files: list[PurePosixPath]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_STORED,
        allowZip64=False,
        strict_timestamps=True,
    ) as archive:
        archive.comment = b""
        for name, relative in expected_zip_entries(files):
            if relative is None:
                archive.writestr(zip_info(name, is_directory=True, mode=0o755), b"")
                continue
            source = TASK_PACK.joinpath(*relative.parts)
            mode = 0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
            archive.writestr(
                zip_info(name, is_directory=False, mode=mode),
                source.read_bytes(),
            )


def atomic_bytes(path: Path, payload: bytes, *, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def build_release() -> str:
    validate_versions()
    files = validate_task_manifest()
    RELEASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(
        prefix=f".{RELEASE_FILENAME}.", suffix=".tmp", dir=RELEASE_PATH.parent
    )
    os.close(descriptor)
    temporary = Path(raw_temporary)
    try:
        render_release(temporary, files)
        temporary.chmod(0o644)
        os.replace(temporary, RELEASE_PATH)
    finally:
        if temporary.exists():
            temporary.unlink()
    return digest_path(RELEASE_PATH)


def expected_registry_entry(release_sha: str) -> dict[str, object]:
    project = "Stock_Skill/bottleneck-serenity-skill"
    skill = f"{project}/task-pack/skill_draft/{STABLE_ID}"
    return {
        "id": STABLE_ID,
        "display_name": STABLE_ID,
        "latest_version": VERSION,
        "version_scheme": VERSION_SCHEME,
        "latest_major": 0,
        "current": True,
        "distribution_mode": "SOURCE_ONLY",
        "local_install_policy": "PROHIBITED",
        "canonical_project_path": project,
        "canonical_skill_path": skill,
        "version_sources": [
            f"{project}/VERSION",
            f"{project}/task-pack/VERSION",
        ],
        "version_claim_paths": CLAIM_PATHS,
        "release": {
            "path": f"{project}/{RELEASE_RELATIVE.as_posix()}",
            "sha256": release_sha,
        },
        "superseded_archives": [],
    }


def validate_discovery_surfaces() -> None:
    for raw in CLAIM_PATHS:
        path = REPO_ROOT.joinpath(*PurePosixPath(raw).parts)
        regular_file(path, "discovery surface")
        text = path.read_text(encoding="utf-8")
        if CLAIM_MARKER not in text:
            raise ReleaseError(f"{raw}: missing exact active claim {CLAIM_MARKER}")
        stale = [marker for marker in STALE_DISCOVERY_MARKERS if marker in text]
        if stale:
            raise ReleaseError(f"{raw}: stale pre-activation marker(s): {stale}")
    project_readme = PROJECT_ROOT / "README.md"
    if f"Version：`{VERSION}`" not in project_readme.read_text(encoding="utf-8"):
        raise ReleaseError("project README lacks the registry validator Version claim")


def render_registry(release_sha: str) -> bytes:
    regular_file(REGISTRY, "registry")
    try:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseError(f"registry JSON is invalid: {exc}") from exc
    if not isinstance(registry, dict):
        raise ReleaseError("registry root must be an object")
    if registry.get("schema_version") != "1.1" or registry.get("registry_id") != "stock-skill":
        raise ReleaseError("registry identity/schema mismatch")
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise ReleaseError("registry skills must be an array")
    matches = [
        (index, entry)
        for index, entry in enumerate(skills)
        if isinstance(entry, dict) and entry.get("id") == STABLE_ID
    ]
    expected = expected_registry_entry(release_sha)
    if len(matches) > 1:
        raise ReleaseError(f"registry contains duplicate {STABLE_ID} entries")
    if matches:
        index, observed = matches[0]
        projection = dict(observed)
        release = projection.get("release")
        if not isinstance(release, dict):
            raise ReleaseError("existing target registry entry has invalid release")
        projected_release = dict(release)
        projected_release["sha256"] = release_sha
        projection["release"] = projected_release
        if projection != expected:
            raise ReleaseError("existing target registry entry drifted from the frozen plan")
        skills[index] = expected
    else:
        skills.append(expected)
    registry["updated_at"] = ACTIVATION_DATE
    return (json.dumps(registry, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def render_backup_manifest(sums_payload: bytes) -> bytes:
    files = collect_files(PROJECT_ROOT, {BACKUP_MANIFEST})
    sums_relative = PurePosixPath("releases/SHA256SUMS")
    files.setdefault(sums_relative, SUMS_PATH)
    lines: list[str] = []
    for relative in sorted(files, key=lambda path: path.as_posix().encode("utf-8")):
        if relative == sums_relative:
            observed = digest_bytes(sums_payload)
        else:
            observed = digest_path(files[relative])
        lines.append(f"{observed}  ./{relative.as_posix()}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def activate_release() -> str:
    validate_versions()
    files = validate_task_manifest()
    validate_discovery_surfaces()
    regular_file(RELEASE_PATH, "release")
    verify_zip(files)
    verify_reproducible_bytes(files)
    release_sha = digest_path(RELEASE_PATH)
    if not SHA256.fullmatch(release_sha):
        raise ReleaseError("release digest is not canonical SHA-256")
    sums_payload = f"{release_sha}  {RELEASE_FILENAME}\n".encode("utf-8")
    registry_payload = render_registry(release_sha)
    backup_payload = render_backup_manifest(sums_payload)
    atomic_bytes(SUMS_PATH, sums_payload)
    atomic_bytes(REGISTRY, registry_payload)
    atomic_bytes(BACKUP_MANIFEST, backup_payload)
    return release_sha


def verify_zip(files: list[PurePosixPath]) -> None:
    regular_file(RELEASE_PATH, "release")
    expected = expected_zip_entries(files)
    expected_names = [name for name, _ in expected]
    try:
        with zipfile.ZipFile(RELEASE_PATH) as archive:
            infos = archive.infolist()
            observed_names = [info.filename for info in infos]
            if observed_names != expected_names or len(set(observed_names)) != len(infos):
                raise ReleaseError("release ZIP entry order/set/uniqueness mismatch")
            if archive.comment:
                raise ReleaseError("release ZIP comment must be empty")
            if archive.testzip() is not None:
                raise ReleaseError("release ZIP CRC verification failed")
            by_name = dict(expected)
            for info in infos:
                canonical_relative(info.filename.rstrip("/"), "ZIP entry")
                if info.date_time != FIXED_TIME:
                    raise ReleaseError(f"{info.filename}: timestamp is not fixed")
                if info.compress_type != zipfile.ZIP_STORED:
                    raise ReleaseError(f"{info.filename}: compression must be ZIP_STORED")
                if info.flag_bits & 0x1:
                    raise ReleaseError(f"{info.filename}: encrypted entry is prohibited")
                if info.create_system != 3 or info.extra or info.comment:
                    raise ReleaseError(f"{info.filename}: non-canonical ZIP metadata")
                unix_mode = (info.external_attr >> 16) & 0xFFFF
                relative = by_name[info.filename]
                if relative is None:
                    if not info.is_dir() or info.file_size != 0:
                        raise ReleaseError(f"{info.filename}: invalid directory entry")
                    if stat.S_IFMT(unix_mode) != stat.S_IFDIR or unix_mode & 0o777 != 0o755:
                        raise ReleaseError(f"{info.filename}: directory mode must be 0755")
                    continue
                if info.is_dir() or stat.S_IFMT(unix_mode) != stat.S_IFREG:
                    raise ReleaseError(f"{info.filename}: must be a regular file")
                source = TASK_PACK.joinpath(*relative.parts)
                expected_mode = 0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
                if unix_mode & 0o777 != expected_mode:
                    raise ReleaseError(
                        f"{info.filename}: expected mode {expected_mode:04o}"
                    )
                if archive.read(info) != source.read_bytes():
                    raise ReleaseError(f"{info.filename}: payload differs from task-pack")
    except (OSError, zipfile.BadZipFile) as exc:
        raise ReleaseError(f"cannot verify release ZIP: {exc}") from exc


def verify_reproducible_bytes(files: list[PurePosixPath]) -> None:
    with tempfile.TemporaryDirectory(prefix="bss-release-verify-") as raw:
        expected = Path(raw) / RELEASE_FILENAME
        render_release(expected, files)
        if expected.read_bytes() != RELEASE_PATH.read_bytes():
            raise ReleaseError("release bytes are not reproducible from current task-pack")


def verify_sha_consumers(release_sha: str) -> None:
    expected_sum = f"{release_sha}  {RELEASE_FILENAME}\n".encode("utf-8")
    regular_file(SUMS_PATH, "SHA256SUMS")
    if SUMS_PATH.read_bytes() != expected_sum:
        raise ReleaseError("SHA256SUMS does not exactly match the release")
    regular_file(REGISTRY, "registry")
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    entries = [
        entry
        for entry in registry.get("skills", [])
        if isinstance(entry, dict) and entry.get("id") == STABLE_ID
    ]
    if entries != [expected_registry_entry(release_sha)]:
        raise ReleaseError("registry target entry differs from the frozen activation plan")
    declared = parse_manifest(
        BACKUP_MANIFEST,
        PROJECT_ROOT,
        excluded={BACKUP_MANIFEST},
    )
    release_entry = declared.get(RELEASE_RELATIVE)
    if release_entry != release_sha:
        raise ReleaseError("backup manifest release entry differs from release SHA")
    task_entries = parse_manifest(
        TASK_MANIFEST,
        TASK_PACK,
        excluded={TASK_MANIFEST},
    )
    if any(".." in path.parts for path in task_entries):
        raise ReleaseError("task manifest contains an outer-project path")


def verify_release() -> str:
    validate_versions()
    validate_discovery_surfaces()
    files = validate_task_manifest()
    verify_zip(files)
    verify_reproducible_bytes(files)
    release_sha = digest_path(RELEASE_PATH)
    verify_sha_consumers(release_sha)
    archives = PROJECT_ROOT / "archives"
    if archives.exists():
        raise ReleaseError("v0.0.0.1 must not create a synthetic archives directory")
    return release_sha


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build, activate, or verify the deterministic v0.0.0.1 release."
    )
    action = parser.add_mutually_exclusive_group()
    action.add_argument(
        "--activate",
        action="store_true",
        help="write the real SHA to SHA256SUMS/registry and generate backup manifest",
    )
    action.add_argument(
        "--verify",
        action="store_true",
        help="verify ZIP reproducibility, metadata, manifests, registry, and SHA DAG",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.verify:
            release_sha = verify_release()
            print(
                f"PASS: {RELEASE_RELATIVE.as_posix()} verified "
                f"(sha256={release_sha})"
            )
        elif args.activate:
            release_sha = activate_release()
            print(
                f"ACTIVATED: {RELEASE_RELATIVE.as_posix()} "
                f"(sha256={release_sha})"
            )
        else:
            build_release()
            print(RELEASE_RELATIVE.as_posix())
    except (OSError, ReleaseError, UnicodeError, json.JSONDecodeError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
