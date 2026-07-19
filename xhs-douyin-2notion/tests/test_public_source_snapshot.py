from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("public_source_snapshot", PROJECT_ROOT / "scripts/public_source_snapshot.py")
assert SPEC and SPEC.loader
SNAPSHOT = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = SNAPSHOT
SPEC.loader.exec_module(SNAPSHOT)


class PublicSourceSnapshotTests(unittest.TestCase):
    def test_only_anonymous_public_github_url_is_allowed(self) -> None:
        valid = "https://github.com/example/project.git"
        self.assertEqual(SNAPSHOT.validate_public_url(valid), valid)
        for invalid in (
            "http://github.com/example/project.git",
            "https://user@example.com/example/project.git",
            "https://github.com/example/project.git?x=1",
            "https://example.com/example/project.git",
        ):
            with self.assertRaises(SNAPSHOT.SnapshotError):
                SNAPSHOT.validate_public_url(invalid)

    def test_environment_is_allowlisted_and_shared_auth_names_are_absent(self) -> None:
        source = {
            "PATH": "/bin",
            "TMPDIR": "/tmp",
            "GH_TOKEN": "synthetic",
            "GITHUB_TOKEN": "synthetic",
            "GIT_CONFIG_GLOBAL": "/unexpected",
        }
        environment = SNAPSHOT.build_isolated_environment(Path("/tmp/isolated"), source)
        self.assertEqual(set(environment), {
            "PATH",
            "HOME",
            "TMPDIR",
            "LC_ALL",
            "LANG",
            "GIT_CONFIG_GLOBAL",
            "GIT_CONFIG_NOSYSTEM",
            "GIT_TERMINAL_PROMPT",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
        })
        self.assertEqual(environment["GIT_CONFIG_GLOBAL"], "/dev/null")
        self.assertEqual(environment["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(environment["GIT_TERMINAL_PROMPT"], "0")
        self.assertNotIn("GH_TOKEN", environment)
        self.assertNotIn("GITHUB_TOKEN", environment)

    def test_every_git_command_disables_credentials(self) -> None:
        commit = "a" * 40
        commands = SNAPSHOT.build_git_commands(
            "https://github.com/example/project.git",
            commit,
            Path("/tmp/snapshot"),
        )
        self.assertEqual(len(commands), 3)
        for command in commands:
            rendered = " ".join(command)
            self.assertIn("credential.helper=", rendered)
            self.assertIn("core.askPass=/usr/bin/false", rendered)


if __name__ == "__main__":
    unittest.main()
