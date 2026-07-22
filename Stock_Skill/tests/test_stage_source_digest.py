#!/usr/bin/env python3
"""Behavioral tests for the complete Stage source digest protocol."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DIGEST_SCRIPT = REPO_ROOT / "Stock_Skill/scripts/digest_stage_source.py"
DIGEST_PATTERN = re.compile(r"^STAGE_SOURCE_SHA256=([0-9a-f]{64})$", re.MULTILINE)


class StageSourceDigestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory(
            prefix="stage-source-digest-fixture-"
        )
        self.repo = Path(self.temporary_directory.name)
        self._git("init", "-q")
        self._git("config", "user.name", "Stage Digest Test")
        self._git("config", "user.email", "stage-digest@example.invalid")
        (self.repo / "tracked.txt").write_text("baseline\n", encoding="utf-8")
        self._git("add", "tracked.txt")
        self._git("commit", "-q", "-m", "baseline")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *arguments],
            cwd=self.repo,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            self.fail(result.stdout + result.stderr)
        return result

    def _run_digest(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(DIGEST_SCRIPT), "--repo-root", str(self.repo)],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )

    def _assert_digest(self, result: subprocess.CompletedProcess[str]) -> str:
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        match = DIGEST_PATTERN.search(result.stdout)
        self.assertIsNotNone(match, result.stdout)
        assert match is not None
        return match.group(1)

    def test_tracks_modified_and_untracked_bytes_deterministically(self) -> None:
        (self.repo / "tracked.txt").write_text("modified\n", encoding="utf-8")
        (self.repo / "new.txt").write_text("first\n", encoding="utf-8")
        first = self._run_digest()
        first_digest = self._assert_digest(first)
        self.assertIn("SUBJECT_PATHS=2", first.stdout)
        self.assertEqual(self._assert_digest(self._run_digest()), first_digest)
        (self.repo / "new.txt").write_text("second\n", encoding="utf-8")
        self.assertNotEqual(self._assert_digest(self._run_digest()), first_digest)

    def test_binds_executable_mode(self) -> None:
        target = self.repo / "tracked.txt"
        target.write_text("modified\n", encoding="utf-8")
        target.chmod(0o644)
        regular_digest = self._assert_digest(self._run_digest())
        target.chmod(0o755)
        executable_digest = self._assert_digest(self._run_digest())
        self.assertNotEqual(regular_digest, executable_digest)

    def test_uses_git_owner_execute_bit_for_mode(self) -> None:
        target = self.repo / "new.txt"
        target.write_text("mode probe\n", encoding="utf-8")
        target.chmod(0o644)
        regular_digest = self._assert_digest(self._run_digest())
        target.chmod(0o654)
        group_execute_digest = self._assert_digest(self._run_digest())
        self.assertEqual(group_execute_digest, regular_digest)

        self._git("add", "new.txt")
        staged_mode = self._git("ls-files", "-s", "--", "new.txt").stdout.split()[0]
        self.assertEqual(staged_mode, "100644")
        self._git("reset", "-q", "--", "new.txt")

        target.chmod(0o755)
        owner_execute_digest = self._assert_digest(self._run_digest())
        self.assertNotEqual(owner_execute_digest, regular_digest)

    def test_represents_deleted_base_blob(self) -> None:
        (self.repo / "tracked.txt").unlink()
        result = self._run_digest()
        self._assert_digest(result)
        self.assertIn("SUBJECT_PATHS=1", result.stdout)

    def test_rejects_nonempty_index(self) -> None:
        (self.repo / "tracked.txt").write_text("staged\n", encoding="utf-8")
        self._git("add", "tracked.txt")
        result = self._run_digest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index must be empty", result.stderr)

    def test_rejects_intent_to_add_index(self) -> None:
        (self.repo / "intent.txt").write_text("intent payload\n", encoding="utf-8")
        self._git("add", "-N", "intent.txt")
        result = self._run_digest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index must be empty", result.stderr)

    def test_rejects_symlink_subject(self) -> None:
        (self.repo / "tracked.txt").unlink()
        (self.repo / "tracked.txt").symlink_to("elsewhere.txt")
        result = self._run_digest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink is prohibited", result.stderr)

    def test_rejects_empty_subject(self) -> None:
        result = self._run_digest()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("subject is empty", result.stderr)


if __name__ == "__main__":
    unittest.main()
