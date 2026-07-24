#!/usr/bin/env python3
"""Durable release, reproducibility, and hash-DAG oracles for BSS."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterator, Mapping


REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_RELATIVE = PurePosixPath("Stock_Skill/bottleneck-serenity-skill")
PROJECT_ROOT = REPO_ROOT.joinpath(*PROJECT_RELATIVE.parts)
TASK_PACK = PROJECT_ROOT / "task-pack"
TASK_MANIFEST = TASK_PACK / "MANIFEST.sha256"
BACKUP_MANIFEST = PROJECT_ROOT / "BACKUP_MANIFEST.sha256"
BUILDER = PROJECT_ROOT / "scripts/build_release.py"
REGISTRY = REPO_ROOT / "Stock_Skill/REGISTRY.json"
RELEASE_FILENAME = (
    "bottleneck-serenity-skill_codex-skill-task-pack_v0.0.0.1.zip"
)
RELEASE_RELATIVE = PurePosixPath("releases") / RELEASE_FILENAME
RELEASE = PROJECT_ROOT.joinpath(*RELEASE_RELATIVE.parts)
SUMS = PROJECT_ROOT / "releases/SHA256SUMS"
ZIP_ROOT = "bottleneck-serenity-skill-task-pack-v0.0.0.1"
LEGACY_ENTRY_PROJECTION_SHA256 = (
    "41232c50c051ebc4b5d2e9503bba6c938b8b6e83f81f69bd322ccfdaeeaf98a0"
)
CLAIM_PATHS = [
    "AGENTS.md",
    "README.md",
    "Stock_Skill/AGENTS.md",
    "Stock_Skill/README.md",
    "Stock_Skill/bottleneck-serenity-skill/AGENTS.md",
    "Stock_Skill/bottleneck-serenity-skill/README.md",
]
INTERFACE_DOCUMENTS = {
    "project-readme": PROJECT_ROOT / "README.md",
    "task-pack-architecture": TASK_PACK / "02_ARCHITECTURE_DATA_API.md",
    "canonical-integration": (
        TASK_PACK
        / "skill_draft/bottleneck-serenity-skill/references/integration_contract.md"
    ),
}
EXPECTED_INPUT_INTERFACE = {
    "schema_version": "1.0",
    "skill_version": "0.0.0.1",
    "request_id": "uuid",
    "query": "研究问题",
    "as_of": "YYYY-MM-DD",
    "source_cutoff": "YYYY-MM-DD",
    "previous_version": None,
    "mode": "scan|deep_dive|compare|monitor|postmortem",
    "universe": {
        "markets": ["US", "AU", "HK"],
        "asset_types": ["equity", "ETF"],
        "min_daily_value_traded_usd": 5000000,
    },
    "horizon_months": 24,
    "risk_constraints": {
        "max_position_weight": 0.10,
        "max_root_driver_weight": 0.30,
        "leverage_allowed": False,
        "derivatives_allowed": False,
    },
    "upstream_artifacts": [],
}
EXPECTED_COMPLETION_INTERFACE = {
    "event_type": "bottleneck_serenity_skill.thesis.completed",
    "schema_version": "1.0",
    "skill_version": "0.0.0.1",
    "request_id": "uuid",
    "thesis_id": "string",
    "as_of": "YYYY-MM-DD",
    "source_cutoff": "YYYY-MM-DD",
    "previous_version": None,
    "decision_file": "decision.json",
    "memo_file": "memo.md",
    "evidence_file": "evidence.json",
    "status": "complete|blocked|partial",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_fences(text: str, label: str) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    for number, match in enumerate(
        re.finditer(r"```json\s*\n(.*?)\n```", text, re.DOTALL), 1
    ):
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"{label}: invalid JSON fence {number}: {exc}") from exc
        if isinstance(value, dict):
            values.append(value)
    return values


def assert_interface_projection(documents: Mapping[str, str]) -> None:
    for label, text in documents.items():
        values = _json_fences(text, label)
        inputs = [
            value
            for value in values
            if "request_id" in value
            and "query" in value
            and "upstream_artifacts" in value
            and "event_type" not in value
        ]
        completions = [
            value
            for value in values
            if value.get("event_type")
            == "bottleneck_serenity_skill.thesis.completed"
        ]
        if len(inputs) != 1:
            raise AssertionError(f"{label}: expected exactly one input projection")
        if len(completions) != 1:
            raise AssertionError(f"{label}: expected exactly one completion projection")
        if inputs[0] != EXPECTED_INPUT_INTERFACE or list(inputs[0]) != list(
            EXPECTED_INPUT_INTERFACE
        ):
            raise AssertionError(f"{label}: input projection drift")
        if completions[0] != EXPECTED_COMPLETION_INTERFACE or list(
            completions[0]
        ) != list(EXPECTED_COMPLETION_INTERFACE):
            raise AssertionError(f"{label}: completion projection drift")


def parse_manifest(
    manifest: Path, base: Path, excluded: set[Path]
) -> dict[str, str]:
    declared: dict[str, str] = {}
    order: list[str] = []
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        match = re.fullmatch(r"([0-9a-f]{64})  \./(.+)", line)
        if match is None:
            raise AssertionError(f"{manifest}:{number}: invalid manifest line")
        raw = match.group(2)
        relative = PurePosixPath(raw)
        if (
            relative.is_absolute()
            or raw != relative.as_posix()
            or ".." in relative.parts
            or raw in declared
        ):
            raise AssertionError(f"{manifest}:{number}: unsafe or duplicate path")
        target = base.joinpath(*relative.parts)
        if target.is_symlink() or not target.is_file():
            raise AssertionError(f"{manifest}:{number}: missing regular file")
        if digest(target) != match.group(1):
            raise AssertionError(f"{manifest}:{number}: SHA-256 mismatch")
        declared[raw] = match.group(1)
        order.append(raw)
    if order != sorted(order, key=lambda value: value.encode("utf-8")):
        raise AssertionError(f"{manifest}: non-canonical entry order")
    actual = {
        path.relative_to(base).as_posix()
        for path in base.rglob("*")
        if path.is_file()
        and path not in excluded
        and "__pycache__" not in path.parts
    }
    if set(declared) != actual:
        raise AssertionError(f"{manifest}: declared/actual file set differs")
    return declared


def expected_zip_entries(files: set[str]) -> dict[str, str | None]:
    expected: dict[str, str | None] = {f"{ZIP_ROOT}/": None}
    for raw in sorted(files, key=lambda value: value.encode("utf-8")):
        parts = PurePosixPath(raw).parts
        for length in range(1, len(parts)):
            expected["/".join((ZIP_ROOT, *parts[:length])) + "/"] = None
        expected["/".join((ZIP_ROOT, *parts))] = raw
    return expected


def expected_registry_entry(release_sha: str) -> dict[str, object]:
    project = PROJECT_RELATIVE.as_posix()
    return {
        "id": "bottleneck-serenity-skill",
        "display_name": "bottleneck-serenity-skill",
        "latest_version": "0.0.0.1",
        "version_scheme": "numeric-quad",
        "latest_major": 0,
        "current": True,
        "distribution_mode": "SOURCE_ONLY",
        "local_install_policy": "PROHIBITED",
        "canonical_project_path": project,
        "canonical_skill_path": (
            f"{project}/task-pack/skill_draft/bottleneck-serenity-skill"
        ),
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


def run_builder(
    root: Path, project: Path, *arguments: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(project / "scripts/build_release.py"), *arguments],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


@contextlib.contextmanager
def isolated_repo() -> Iterator[tuple[Path, Path]]:
    with tempfile.TemporaryDirectory(prefix="bss-release-test-") as raw:
        root = Path(raw)
        stock = root / "Stock_Skill"
        stock.mkdir()
        for name in ("AGENTS.md", "README.md"):
            shutil.copy2(REPO_ROOT / name, root / name)
        for name in ("AGENTS.md", "README.md", "REGISTRY.json"):
            shutil.copy2(REPO_ROOT / "Stock_Skill" / name, stock / name)
        project = root.joinpath(*PROJECT_RELATIVE.parts)
        shutil.copytree(PROJECT_ROOT, project, symlinks=True)
        yield root, project


def rewrite_task_manifest(project: Path) -> None:
    task_pack = project / "task-pack"
    manifest = task_pack / "MANIFEST.sha256"
    files = sorted(
        (
            path
            for path in task_pack.rglob("*")
            if path.is_file() and path != manifest and "__pycache__" not in path.parts
        ),
        key=lambda path: path.relative_to(task_pack).as_posix().encode("utf-8"),
    )
    manifest.write_text(
        "".join(
            f"{digest(path)}  ./{path.relative_to(task_pack).as_posix()}\n"
            for path in files
        ),
        encoding="utf-8",
    )


class BottleneckSerenityReleaseTests(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.locked = {
            path: digest(path)
            for path in (RELEASE, SUMS, REGISTRY, TASK_MANIFEST, BACKUP_MANIFEST)
        }

    def tearDown(self) -> None:
        for path, expected in self.locked.items():
            self.assertEqual(digest(path), expected, f"active artifact mutated: {path}")

    def test_active_release_zip_registry_and_hash_dag(self) -> None:
        result = run_builder(REPO_ROOT, PROJECT_ROOT, "--verify")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS: releases/", result.stdout)

        task_entries = parse_manifest(TASK_MANIFEST, TASK_PACK, {TASK_MANIFEST})
        backup_entries = parse_manifest(
            BACKUP_MANIFEST, PROJECT_ROOT, {BACKUP_MANIFEST}
        )
        release_sha = digest(RELEASE)
        self.assertEqual(backup_entries[RELEASE_RELATIVE.as_posix()], release_sha)
        self.assertIn("releases/SHA256SUMS", backup_entries)
        self.assertIn("scripts/build_release.py", backup_entries)
        self.assertFalse(any(path.startswith("releases/") for path in task_entries))

        release_files = set(task_entries) | {"MANIFEST.sha256"}
        expected = expected_zip_entries(release_files)
        expected_names = sorted(expected, key=lambda value: value.encode("utf-8"))
        with zipfile.ZipFile(RELEASE) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            self.assertEqual(names, expected_names)
            self.assertEqual(len(names), len(set(names)))
            self.assertEqual(archive.comment, b"")
            self.assertIsNone(archive.testzip())
            payloads: list[bytes] = []
            for info in infos:
                self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.extra, b"")
                self.assertEqual(info.comment, b"")
                self.assertFalse(info.flag_bits & 0x1)
                mode = (info.external_attr >> 16) & 0xFFFF
                raw = expected[info.filename]
                if raw is None:
                    self.assertTrue(info.is_dir())
                    self.assertEqual(info.file_size, 0)
                    self.assertEqual(stat.S_IFMT(mode), stat.S_IFDIR)
                    self.assertEqual(mode & 0o777, 0o755)
                    continue
                source = TASK_PACK.joinpath(*PurePosixPath(raw).parts)
                expected_mode = (
                    0o755 if source.stat().st_mode & stat.S_IXUSR else 0o644
                )
                self.assertFalse(info.is_dir())
                self.assertEqual(stat.S_IFMT(mode), stat.S_IFREG)
                self.assertEqual(mode & 0o777, expected_mode)
                payload = archive.read(info)
                self.assertEqual(payload, source.read_bytes())
                payloads.append(payload)
        release_payload = b"\n".join(payloads)
        self.assertIsNone(
            re.search(rb"constraint[-_ ]alpha", release_payload, re.IGNORECASE)
        )
        self.assertNotIn(release_sha.encode("ascii"), release_payload)

        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        entries = {entry["id"]: entry for entry in registry["skills"]}
        self.assertEqual(
            entries["bottleneck-serenity-skill"],
            expected_registry_entry(release_sha),
        )
        legacy = dict(entries["stock-commercial-opportunities"])
        self.assertEqual(legacy.pop("version_scheme"), "semver")
        projection = json.dumps(
            legacy, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(projection).hexdigest(),
            LEGACY_ENTRY_PROJECTION_SHA256,
        )
        self.assertEqual(
            SUMS.read_text(encoding="utf-8"),
            f"{release_sha}  {RELEASE_FILENAME}\n",
        )

        consumers: list[str] = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            try:
                if release_sha in path.read_text(encoding="utf-8"):
                    consumers.append(path.relative_to(REPO_ROOT).as_posix())
            except (OSError, UnicodeDecodeError):
                continue
        self.assertEqual(
            sorted(consumers),
            sorted(
                [
                    "Stock_Skill/REGISTRY.json",
                    "Stock_Skill/bottleneck-serenity-skill/"
                    "BACKUP_MANIFEST.sha256",
                    "Stock_Skill/bottleneck-serenity-skill/"
                    "releases/SHA256SUMS",
                ]
            ),
        )
        self.assertFalse((PROJECT_ROOT / "archives").exists())

    def test_machine_interface_projection_is_exact_across_documents(self) -> None:
        documents = {
            label: path.read_text(encoding="utf-8")
            for label, path in INTERFACE_DOCUMENTS.items()
        }
        assert_interface_projection(documents)

    def test_machine_interface_projection_mutations_fail_closed(self) -> None:
        documents = {
            label: path.read_text(encoding="utf-8")
            for label, path in INTERFACE_DOCUMENTS.items()
        }
        missing = dict(documents)
        missing["canonical-integration"] = missing["canonical-integration"].replace(
            '  "source_cutoff": "YYYY-MM-DD",\n', "", 1
        )
        with self.subTest(mutation="missing-input-field"), self.assertRaises(
            AssertionError
        ):
            assert_interface_projection(missing)

        renamed = dict(documents)
        renamed["canonical-integration"] = renamed["canonical-integration"].replace(
            '  "query": "研究问题",', '  "question": "研究问题",', 1
        )
        with self.subTest(mutation="renamed-input-field"), self.assertRaises(
            AssertionError
        ):
            assert_interface_projection(renamed)

        completion = dict(documents)
        before, marker, after = completion["canonical-integration"].partition(
            '  "event_type": "bottleneck_serenity_skill.thesis.completed",'
        )
        self.assertTrue(marker)
        after = after.replace('"skill_version"', '"skillVersion"', 1)
        completion["canonical-integration"] = before + marker + after
        with self.subTest(mutation="renamed-completion-field"), self.assertRaises(
            AssertionError
        ):
            assert_interface_projection(completion)

    def test_clean_build_is_byte_identical_in_isolation(self) -> None:
        with isolated_repo() as (root, project):
            first = run_builder(root, project)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            release = project.joinpath(*RELEASE_RELATIVE.parts)
            first_payload = release.read_bytes()
            second = run_builder(root, project)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(release.read_bytes(), first_payload)
            verified = run_builder(root, project, "--verify")
            self.assertEqual(
                verified.returncode, 0, verified.stdout + verified.stderr
            )

    def test_activate_rejects_release_from_stale_task_pack(self) -> None:
        with isolated_repo() as (root, project):
            changelog = project / "task-pack/CHANGELOG.md"
            changelog.write_text(
                changelog.read_text(encoding="utf-8") + "\nfixture drift\n",
                encoding="utf-8",
            )
            rewrite_task_manifest(project)
            result = run_builder(root, project, "--activate")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("payload differs from task-pack", result.stderr)

    def test_verify_rejects_artifact_or_discovery_drift(self) -> None:
        def corrupt_release(root: Path, project: Path) -> None:
            release = project.joinpath(*RELEASE_RELATIVE.parts)
            release.write_bytes(release.read_bytes() + b"corrupt")

        def corrupt_sums(root: Path, project: Path) -> None:
            (project / "releases/SHA256SUMS").write_text(
                ("0" * 64) + f"  {RELEASE_FILENAME}\n", encoding="utf-8"
            )

        def corrupt_registry(root: Path, project: Path) -> None:
            path = root / "Stock_Skill/REGISTRY.json"
            registry = json.loads(path.read_text(encoding="utf-8"))
            entry = next(
                item
                for item in registry["skills"]
                if item["id"] == "bottleneck-serenity-skill"
            )
            entry["release"]["sha256"] = "0" * 64
            path.write_text(
                json.dumps(registry, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        def corrupt_backup(root: Path, project: Path) -> None:
            (project / "BACKUP_MANIFEST.sha256").write_text(
                "invalid\n", encoding="utf-8"
            )

        def stale_discovery(root: Path, project: Path) -> None:
            path = project / "README.md"
            path.write_text(
                path.read_text(encoding="utf-8") + "\nREGISTRY_NOT_ACTIVE\n",
                encoding="utf-8",
            )

        cases = (
            ("release", corrupt_release),
            ("sums", corrupt_sums),
            ("registry", corrupt_registry),
            ("backup", corrupt_backup),
            ("discovery", stale_discovery),
        )
        for name, mutate in cases:
            with self.subTest(name=name), isolated_repo() as (root, project):
                mutate(root, project)
                result = run_builder(root, project, "--verify")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("FAIL:", result.stderr)

    def test_build_rejects_manifest_drift_and_symlink(self) -> None:
        with self.subTest(name="manifest-drift"), isolated_repo() as (root, project):
            version = project / "task-pack/VERSION"
            version.write_bytes(version.read_bytes() + b"drift")
            result = run_builder(root, project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)

        with self.subTest(name="symlink"), isolated_repo() as (root, project):
            os.symlink("VERSION", project / "task-pack/linked-version")
            result = run_builder(root, project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("FAIL:", result.stderr)


if __name__ == "__main__":
    unittest.main()
