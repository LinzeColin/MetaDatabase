#!/usr/bin/env python3
"""Fail-closed validator for MetaDatabase's stock Skill registry."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
NUMERIC_QUAD = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"
)
VERSION_SCHEMES: dict[str, re.Pattern[str]] = {
    "semver": SEMVER,
    "numeric-quad": NUMERIC_QUAD,
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def parse_version(raw: object, scheme: object) -> tuple[int, ...] | None:
    """Return a canonical numeric tuple for a known scheme, otherwise None."""
    if not isinstance(raw, str) or not isinstance(scheme, str):
        return None
    pattern = VERSION_SCHEMES.get(scheme)
    if pattern is None or not pattern.fullmatch(raw):
        return None
    try:
        return tuple(int(part) for part in raw.split("."))
    except ValueError:
        return None


def compare_versions(
    left: object,
    left_scheme: object,
    right: object,
    right_scheme: object,
) -> int:
    """Compare canonical versions only when both use the same known scheme."""
    if (
        not isinstance(left_scheme, str)
        or not isinstance(right_scheme, str)
        or left_scheme != right_scheme
        or left_scheme not in VERSION_SCHEMES
    ):
        raise ValueError("versions must use the same known version scheme")
    left_tuple = parse_version(left, left_scheme)
    right_tuple = parse_version(right, right_scheme)
    if left_tuple is None or right_tuple is None:
        raise ValueError("version is not canonical for its scheme")
    return (left_tuple > right_tuple) - (left_tuple < right_tuple)


def display_version_label(version: str, scheme: str, major: int) -> str:
    """Preserve the semver major alias and show numeric-quad versions in full."""
    if scheme == "semver":
        return f"v{major}"
    if scheme == "numeric-quad":
        return f"v{version}"
    raise ValueError("unknown version scheme")


def validate_version_model(
    item: dict[str, object], label: str, errors: list[str]
) -> tuple[str, str, tuple[int, ...]] | None:
    """Validate one entry's scheme, latest version, major, and archive lineage."""
    scheme = item.get("version_scheme")
    if not isinstance(scheme, str) or scheme not in VERSION_SCHEMES:
        errors.append(f"{label}: invalid version_scheme")
        return None

    version = item.get("latest_version")
    if not isinstance(version, str):
        errors.append(f"{label}: invalid latest_version for version_scheme {scheme}")
        return None
    latest_tuple = parse_version(version, scheme)
    if latest_tuple is None:
        errors.append(f"{label}: invalid latest_version for version_scheme {scheme}")
        return None

    major = item.get("latest_major")
    if type(major) is not int or major != latest_tuple[0]:
        errors.append(f"{label}: latest_major does not match latest_version")

    archives = item.get("superseded_archives")
    if not isinstance(archives, list):
        errors.append(f"{label}: superseded_archives must be an array")
        archives = []

    archive_versions: set[str] = set()
    for archive_index, archive in enumerate(archives):
        archive_label = f"{label}.superseded_archives[{archive_index}]"
        if not isinstance(archive, dict):
            errors.append(f"{archive_label}: must be an object")
            continue
        if "version_scheme" in archive:
            errors.append(f"{archive_label}: version_scheme must be inherited from its Skill entry")
        archive_version = archive.get("version")
        try:
            comparison = compare_versions(archive_version, scheme, version, scheme)
        except ValueError:
            errors.append(f"{archive_label}: invalid version for version_scheme {scheme}")
            continue
        if comparison >= 0:
            errors.append(f"{archive_label}: version must be older than latest")
        if archive_version in archive_versions:
            errors.append(f"{archive_label}: duplicate version")
        archive_versions.add(archive_version)

    return scheme, version, latest_tuple


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_repo_path(repo_root: Path, raw: object, label: str, errors: list[str]) -> Path:
    if not isinstance(raw, str) or not raw:
        errors.append(f"{label}: path must be a non-empty string")
        return repo_root / "__INVALID__"
    posix = PurePosixPath(raw)
    if posix.is_absolute() or ".." in posix.parts or raw != posix.as_posix():
        errors.append(f"{label}: unsafe or non-canonical path {raw!r}")
        return repo_root / "__INVALID__"
    path = repo_root.joinpath(*posix.parts)
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        errors.append(f"{label}: path escapes repository")
    return path


def check_hash(path: Path, expected: object, label: str, errors: list[str]) -> None:
    if not path.is_file():
        errors.append(f"{label}: missing file {path}")
        return
    if not isinstance(expected, str) or not SHA256.fullmatch(expected):
        errors.append(f"{label}: invalid SHA-256 declaration")
        return
    actual = digest(path)
    if actual != expected:
        errors.append(f"{label}: SHA-256 mismatch: expected {expected}, got {actual}")


def check_manifest(manifest: Path, base: Path, excluded: set[Path], errors: list[str]) -> None:
    if not manifest.is_file():
        errors.append(f"manifest missing: {manifest}")
        return
    listed: set[Path] = set()
    for number, raw in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", raw)
        if not match:
            errors.append(f"{manifest}:{number}: invalid manifest line")
            continue
        raw_relative = match.group(2)
        posix = PurePosixPath(raw_relative)
        if posix.is_absolute() or ".." in posix.parts or raw_relative != posix.as_posix():
            errors.append(f"{manifest}:{number}: unsafe manifest path")
            continue
        relative = Path(*posix.parts)
        target = base / relative
        listed.add(relative)
        check_hash(target, match.group(1), f"{manifest.name}:{relative}", errors)
    actual = {
        path.relative_to(base)
        for path in base.rglob("*")
        if path.is_file() and path not in excluded and "__pycache__" not in path.parts
    }
    if listed != actual:
        missing = sorted(str(path) for path in actual - listed)
        stale = sorted(str(path) for path in listed - actual)
        if missing:
            errors.append(f"{manifest.name}: unlisted files: {', '.join(missing)}")
        if stale:
            errors.append(f"{manifest.name}: stale entries: {', '.join(stale)}")


def frontmatter_name(skill_md: Path, errors: list[str]) -> str | None:
    if not skill_md.is_file():
        errors.append(f"missing Skill entrypoint: {skill_md}")
        return None
    text = skill_md.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, flags=re.DOTALL)
    if not match:
        errors.append(f"invalid Skill frontmatter: {skill_md}")
        return None
    name_lines = re.findall(r"^name:\s*(.+?)\s*$", match.group(1), flags=re.MULTILINE)
    if len(name_lines) != 1:
        errors.append(f"Skill frontmatter must contain exactly one name: {skill_md}")
        return None
    return name_lines[0].strip('"\'')


def main() -> int:
    stock_root = Path(__file__).resolve().parents[1]
    repo_root = stock_root.parent
    registry_path = stock_root / "REGISTRY.json"
    errors: list[str] = []

    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read registry: {exc}", file=sys.stderr)
        return 1

    if not isinstance(registry, dict):
        print("FAIL: stock Skill registry root must be an object", file=sys.stderr)
        return 1

    if registry.get("schema_version") != "1.1":
        errors.append("schema_version must be 1.1")
    if registry.get("registry_id") != "stock-skill":
        errors.append("registry_id must be stock-skill")

    for raw in registry.get("legacy_paths_must_not_exist", []):
        legacy = safe_repo_path(repo_root, raw, "legacy path", errors)
        if legacy.exists():
            errors.append(f"legacy path must not exist: {raw}")

    skills = registry.get("skills")
    if not isinstance(skills, list) or not skills:
        errors.append("skills must be a non-empty list")
        skills = []

    seen_ids: set[str] = set()
    currents: list[tuple[str, str, str, int]] = []
    for index, item in enumerate(skills):
        label = f"skills[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: must be an object")
            continue
        skill_id = item.get("id")
        if not isinstance(skill_id, str) or not re.fullmatch(r"[a-z0-9-]{1,63}", skill_id):
            errors.append(f"{label}: invalid id")
            continue
        if skill_id in seen_ids:
            errors.append(f"{label}: duplicate id {skill_id}")
        seen_ids.add(skill_id)
        version_model = validate_version_model(item, label, errors)
        if version_model is None:
            continue
        scheme, version, latest_tuple = version_model
        if item.get("current") is not True:
            errors.append(f"{label}: current must be true")
        if item.get("distribution_mode") != "SOURCE_ONLY":
            errors.append(f"{label}: distribution_mode must be SOURCE_ONLY")
        if item.get("local_install_policy") != "PROHIBITED":
            errors.append(f"{label}: local_install_policy must be PROHIBITED")

        project_raw = item.get("canonical_project_path")
        project = safe_repo_path(repo_root, project_raw, f"{label}.canonical_project_path", errors)
        skill = safe_repo_path(repo_root, item.get("canonical_skill_path"), f"{label}.canonical_skill_path", errors)
        if not project.is_dir():
            errors.append(f"{label}: canonical project directory missing")
        if not skill.is_dir() or skill.name != skill_id:
            errors.append(f"{label}: canonical Skill directory missing or ID mismatch")

        version_sources = item.get("version_sources")
        if not isinstance(version_sources, list) or not version_sources:
            errors.append(f"{label}: version_sources must be non-empty")
        else:
            required_sources = {
                f"{project_raw}/VERSION",
                f"{project_raw}/task-pack/VERSION",
            }
            declared_sources = {raw for raw in version_sources if isinstance(raw, str)}
            if not required_sources.issubset(declared_sources):
                errors.append(f"{label}: version_sources omits a required VERSION file")
            for source_index, raw in enumerate(version_sources):
                source = safe_repo_path(repo_root, raw, f"{label}.version_sources[{source_index}]", errors)
                try:
                    observed = source.read_text(encoding="utf-8").strip()
                except OSError:
                    errors.append(f"{label}: missing version source {raw}")
                else:
                    if observed != version:
                        errors.append(f"{label}: {raw} says {observed!r}, expected {version}")

        claim_paths = item.get("version_claim_paths")
        if not isinstance(claim_paths, list) or not claim_paths:
            errors.append(f"{label}: version_claim_paths must be non-empty")
        else:
            required_claims = {
                "AGENTS.md",
                "README.md",
                "Stock_Skill/AGENTS.md",
                "Stock_Skill/README.md",
                f"{project_raw}/AGENTS.md",
                f"{project_raw}/README.md",
            }
            declared_claims = {raw for raw in claim_paths if isinstance(raw, str)}
            if not required_claims.issubset(declared_claims):
                errors.append(f"{label}: version_claim_paths omits a required agent discovery surface")
            for claim_index, raw in enumerate(claim_paths):
                claim = safe_repo_path(repo_root, raw, f"{label}.version_claim_paths[{claim_index}]", errors)
                try:
                    claim_text = claim.read_text(encoding="utf-8")
                except OSError:
                    errors.append(f"{label}: missing version claim file {raw}")
                else:
                    if skill_id not in claim_text or version not in claim_text:
                        errors.append(f"{label}: {raw} does not declare {skill_id}={version}")

        if frontmatter_name(skill / "SKILL.md", errors) != skill_id:
            errors.append(f"{label}: SKILL.md name does not match {skill_id}")
        openai_yaml = skill / "agents" / "openai.yaml"
        if not openai_yaml.is_file():
            errors.append(f"{label}: missing agents/openai.yaml")
        else:
            metadata = openai_yaml.read_text(encoding="utf-8")
            display_name = item.get("display_name")
            if not isinstance(display_name, str) or not display_name:
                errors.append(f"{label}: display_name must be a non-empty string")
            elif display_name not in metadata:
                errors.append(f"{label}: display_name is stale in agents/openai.yaml")
            if f"${skill_id}" not in metadata:
                errors.append(f"{label}: default_prompt does not invoke ${skill_id}")

        release = item.get("release")
        if not isinstance(release, dict):
            errors.append(f"{label}: release must be an object")
        else:
            release_path = safe_repo_path(repo_root, release.get("path"), f"{label}.release.path", errors)
            check_hash(release_path, release.get("sha256"), f"{label}.release", errors)
            if version not in release_path.name:
                errors.append(f"{label}: release filename does not contain latest_version")
            sums = project / "releases" / "SHA256SUMS"
            expected_sum = f"{release.get('sha256')}  {release_path.name}"
            if not sums.is_file() or expected_sum not in sums.read_text(encoding="utf-8").splitlines():
                errors.append(f"{label}: releases/SHA256SUMS does not match registry release")

        archives = item.get("superseded_archives")
        if isinstance(archives, list):
            for archive_index, archive in enumerate(archives):
                archive_label = f"{label}.superseded_archives[{archive_index}]"
                if not isinstance(archive, dict):
                    continue
                if archive.get("status") != "ARCHIVE_ONLY":
                    errors.append(f"{archive_label}: status must be ARCHIVE_ONLY")
                archive_path = safe_repo_path(repo_root, archive.get("path"), f"{archive_label}.path", errors)
                check_hash(archive_path, archive.get("sha256"), archive_label, errors)

        readme = project / "README.md"
        if not readme.is_file() or f"Version：`{version}`" not in readme.read_text(encoding="utf-8"):
            errors.append(f"{label}: project README current version is stale")
        backup_manifest = project / "BACKUP_MANIFEST.sha256"
        check_manifest(backup_manifest, project, {backup_manifest}, errors)
        task_pack = project / "task-pack"
        task_manifest = task_pack / "MANIFEST.sha256"
        check_manifest(task_manifest, task_pack, {task_manifest}, errors)
        currents.append((skill_id, version, scheme, latest_tuple[0]))

    if errors:
        print(f"FAIL: stock Skill registry invalid ({len(errors)} error(s))", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    print("PASS: stock Skill registry valid")
    for skill_id, version, scheme, major in currents:
        print(f"CURRENT: {skill_id}={version} ({display_version_label(version, scheme, major)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
