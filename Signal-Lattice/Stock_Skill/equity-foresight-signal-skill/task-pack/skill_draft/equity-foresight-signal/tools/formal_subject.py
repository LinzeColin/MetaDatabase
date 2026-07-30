from __future__ import annotations

import hashlib
import json
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Iterable

STABLE_ID = "equity-foresight-signal"
ROOT_FILE_SOURCES: tuple[tuple[str, str], ...] = (
    ("SKILL.md", f"taskpack_blueprint/skill_draft/{STABLE_ID}/SKILL.md"),
    ("agents/openai.yaml", f"taskpack_blueprint/skill_draft/{STABLE_ID}/agents/openai.yaml"),
    ("README.md", "README.md"),
    ("VERSION", "VERSION"),
    ("CHANGELOG.md", "CHANGELOG.md"),
    ("FUTURE_ROADMAP.md", "FUTURE_ROADMAP.md"),
    ("SOURCE_INVENTORY.md", "SOURCE_INVENTORY.md"),
    ("LICENSE_AND_ATTRIBUTION.md", "LICENSE_AND_ATTRIBUTION.md"),
    ("build_fixtures.py", "build_fixtures.py"),
)
TREE_SOURCES: tuple[tuple[str, str], ...] = (
    ("equity_foresight_signal", "equity_foresight_signal"),
    ("fixtures", "fixtures"),
    ("evidence", "evidence"),
    ("docs", "docs"),
)
TOOL_FILES: tuple[str, ...] = (
    "benchmark_capacity.py",
    "context_capture.py",
    "formal_subject.py",
    "import_legacy_backtest.py",
    "run_kernel_isolation.py",
    "run_network_namespace_isolation.py",
    "run_portability_matrix.py",
    "run_release_oracles.py",
    "seal_snapshot.py",
    "verify_formal_runtime.py",
    "verify_macos_zero_footprint.py",
    "verify_target_entry.py",
)
TEST_FILES: tuple[str, ...] = (
    "test_capacity.py",
    "test_cli_operations.py",
    "test_dataset.py",
    "test_engine.py",
    "test_formal_runtime_verifier.py",
    "test_host.py",
    "test_kernel_isolation.py",
    "test_legacy_evidence.py",
    "test_macos_zero_footprint.py",
    "test_network_namespace_isolation.py",
    "test_portability.py",
    "test_runtime_operations.py",
    "test_training.py",
)
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
EXCLUDED_NAMES = {".coverage", ".DS_Store"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".swp"}


def _canonical_object_sha256(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _safe_relative(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    pure = PurePosixPath(normalized)
    if value != normalized or not normalized or pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe or non-canonical Subject path: {value}")
    return normalized


def _hash_file(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Subject source must be a regular file: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_row(rows: dict[str, str], destination: str, source: Path) -> None:
    destination = _safe_relative(destination)
    if destination in rows:
        raise ValueError(f"duplicate Subject destination: {destination}")
    rows[destination] = _hash_file(source)


def _iter_source_tree(source_root: Path, destination_prefix: str) -> Iterable[tuple[str, Path]]:
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError(f"Subject tree source missing/unsafe: {source_root}")
    for path in sorted(source_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"symlink forbidden in Subject tree: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(source_root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        yield f"{destination_prefix}/{rel.as_posix()}", path


def source_subject_rows(source_root: Path) -> list[dict[str, str]]:
    """Return the exact final installed Skill file inventory from the source layout."""
    source_root = source_root.resolve()
    rows: dict[str, str] = {}
    for destination, source_relative in ROOT_FILE_SOURCES:
        _add_row(rows, destination, source_root / source_relative)
    for destination_prefix, source_relative in TREE_SOURCES:
        for destination, source in _iter_source_tree(source_root / source_relative, destination_prefix):
            _add_row(rows, destination, source)
    for name in TOOL_FILES:
        _add_row(rows, f"tools/{name}", source_root / "tools" / name)
    for name in TEST_FILES:
        _add_row(rows, f"tests/{name}", source_root / "tests" / name)
    return [{"path": path, "sha256": rows[path]} for path in sorted(rows)]


def packaged_subject_rows(skill_root: Path) -> list[dict[str, str]]:
    """Hash every regular file in an assembled final installed Skill tree."""
    skill_root = skill_root.resolve()
    if skill_root.is_symlink() or not skill_root.is_dir():
        raise ValueError(f"packaged Subject root missing/unsafe: {skill_root}")
    rows: dict[str, str] = {}
    for path in sorted(skill_root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise ValueError(f"symlink forbidden in packaged Subject: {path}")
        if not path.is_file():
            continue
        rel = path.relative_to(skill_root)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        if path.name in EXCLUDED_NAMES or path.suffix in EXCLUDED_SUFFIXES:
            continue
        _add_row(rows, rel.as_posix(), path)
    if not rows:
        raise ValueError("packaged Subject is empty")
    return [{"path": path, "sha256": rows[path]} for path in sorted(rows)]


def source_subject_sha256(source_root: Path) -> str:
    return _canonical_object_sha256(source_subject_rows(source_root))


def packaged_subject_sha256(skill_root: Path) -> str:
    return _canonical_object_sha256(packaged_subject_rows(skill_root))
