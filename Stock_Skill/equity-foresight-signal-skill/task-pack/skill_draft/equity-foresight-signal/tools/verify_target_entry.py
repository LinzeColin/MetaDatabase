from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath

STABLE_ID = "equity-foresight-signal"
VERSION = "0.0.0.1"
PROJECT_REL = Path("Stock_Skill/equity-foresight-signal-skill")
SKILL_REL = PROJECT_REL / "task-pack/skill_draft/equity-foresight-signal"
RELEASE_NAME = "equity-foresight-signal_codex-skill-task-pack_v0.0.0.1.zip"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def safe_path(repo: Path, raw: str) -> Path:
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or ".." in pure.parts or raw != pure.as_posix():
        raise ValueError(f"unsafe path: {raw!r}")
    path = repo.joinpath(*pure.parts)
    path.resolve().relative_to(repo.resolve())
    return path


def verify_manifest(manifest: Path, base: Path, excluded: set[Path]) -> int:
    if not manifest.is_file():
        raise ValueError(f"missing manifest: {manifest}")
    listed: dict[Path, str] = {}
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if not match:
            raise ValueError(f"invalid manifest line {manifest}:{number}")
        rel = Path(*PurePosixPath(match.group(2)).parts)
        if rel in listed:
            raise ValueError(f"duplicate manifest path: {rel}")
        listed[rel] = match.group(1)
    actual = {
        path.relative_to(base): digest(path)
        for path in base.rglob("*")
        if path.is_file() and not path.is_symlink() and path not in excluded and "__pycache__" not in path.parts
    }
    if listed != actual:
        missing = sorted(str(path) for path in actual.keys() - listed.keys())
        stale = sorted(str(path) for path in listed.keys() - actual.keys())
        changed = sorted(str(path) for path in listed.keys() & actual.keys() if listed[path] != actual[path])
        raise ValueError(json.dumps({"manifest": str(manifest), "missing": missing, "stale": stale, "changed": changed}, sort_keys=True))
    return len(actual)


def verify(repo: Path) -> dict[str, object]:
    repo = repo.resolve()
    registry = json.loads((repo / "Stock_Skill/REGISTRY.json").read_text(encoding="utf-8"))
    entries = [item for item in registry.get("skills", []) if item.get("id") == STABLE_ID]
    if len(entries) != 1:
        raise ValueError("target registry must contain exactly one target entry")
    entry = entries[0]
    expected = {
        "latest_version": VERSION,
        "version_scheme": "numeric-quad",
        "latest_major": 0,
        "current": True,
        "distribution_mode": "SOURCE_ONLY",
        "local_install_policy": "PROHIBITED",
        "canonical_project_path": PROJECT_REL.as_posix(),
        "canonical_skill_path": SKILL_REL.as_posix(),
        "superseded_archives": [],
    }
    for key, value in expected.items():
        if entry.get(key) != value:
            raise ValueError(f"registry field mismatch: {key}")
    project = repo / PROJECT_REL
    skill = repo / SKILL_REL
    for path in (project, skill):
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"missing safe directory: {path}")
    if (project / "VERSION").read_text(encoding="utf-8").strip() != VERSION:
        raise ValueError("project VERSION mismatch")
    if (project / "task-pack/VERSION").read_text(encoding="utf-8").strip() != VERSION:
        raise ValueError("task-pack VERSION mismatch")
    for raw in entry["version_claim_paths"]:
        text = safe_path(repo, raw).read_text(encoding="utf-8")
        if STABLE_ID not in text or VERSION not in text:
            raise ValueError(f"version claim mismatch: {raw}")
    skill_text = (skill / "SKILL.md").read_text(encoding="utf-8")
    if not skill_text.startswith("---\n") or f"name: {STABLE_ID}" not in skill_text.split("---", 2)[1]:
        raise ValueError("SKILL.md identity mismatch")
    metadata = (skill / "agents/openai.yaml").read_text(encoding="utf-8")
    if "股势前瞻" not in metadata or f"${STABLE_ID}" not in metadata:
        raise ValueError("agents/openai.yaml mismatch")
    release = project / "releases" / RELEASE_NAME
    declared = entry.get("release")
    if not isinstance(declared, dict) or declared.get("path") != (PROJECT_REL / "releases" / RELEASE_NAME).as_posix():
        raise ValueError("release path mismatch")
    release_hash = digest(release)
    if declared.get("sha256") != release_hash or not SHA256.fullmatch(release_hash):
        raise ValueError("release hash mismatch")
    expected_sum = f"{release_hash}  {RELEASE_NAME}"
    if expected_sum not in (project / "releases/SHA256SUMS").read_text(encoding="utf-8").splitlines():
        raise ValueError("release SHA256SUMS mismatch")
    project_count = verify_manifest(project / "BACKUP_MANIFEST.sha256", project, {project / "BACKUP_MANIFEST.sha256"})
    task = project / "task-pack"
    task_count = verify_manifest(task / "MANIFEST.sha256", task, {task / "MANIFEST.sha256"})
    system_card = (project / "SYSTEM_CARD.md").read_text(encoding="utf-8")
    if "SHADOW_ONLY" not in system_card or "OUTCOME_NOT_PROVEN" not in system_card:
        raise ValueError("project capability boundary missing")
    return {
        "schema": "efs.target_entry_verification.v1",
        "status": "PASS",
        "stable_id": STABLE_ID,
        "version": VERSION,
        "release_sha256": release_hash,
        "project_manifest_file_count": project_count,
        "task_manifest_file_count": task_count,
        "capability_ceiling": "SHADOW_ONLY",
        "outcome_status": "NOT_PROVEN",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("repo", type=Path)
    args = parser.parse_args()
    try:
        report = verify(args.repo)
    except Exception as exc:
        report = {"schema": "efs.target_entry_verification.v1", "status": "FAIL", "error_type": type(exc).__name__, "message": str(exc)}
        print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
