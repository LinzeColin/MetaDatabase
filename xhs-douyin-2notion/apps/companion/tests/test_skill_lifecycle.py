from __future__ import annotations

import unittest

from x2n_companion import skill_lifecycle


class SkillLifecycleTests(unittest.TestCase):
    def test_all_copyable_source_lifecycle_commands_pass_without_runtime_writes(self) -> None:
        commands = (
            ("install",),
            ("self-test",),
            ("canary", "--synthetic"),
            ("upgrade", "--dry-run"),
            ("rollback", "--dry-run"),
            ("diagnose",),
            ("uninstall", "--dry-run", "--retain-data"),
        )
        for command in commands:
            with self.subTest(command=command):
                receipt = skill_lifecycle.run(skill_lifecycle.build_parser().parse_args(command))
                self.assertEqual(receipt["status"], "PASS")
                self.assertEqual(receipt["platform_calls"], 0)
                self.assertEqual(receipt["runtime_writes"], 0)
                self.assertEqual(receipt["product_lifecycle"], "REAL_INSTALL_AND_MVP_DEPLOYMENT_NOT_RUN")

    def test_real_or_destructive_lifecycle_actions_fail_closed(self) -> None:
        rejected = (
            ("canary",),
            ("upgrade",),
            ("rollback",),
            ("uninstall", "--dry-run"),
        )
        for command in rejected:
            with self.subTest(command=command):
                with self.assertRaises(skill_lifecycle.SkillLifecycleError):
                    skill_lifecycle.run(skill_lifecycle.build_parser().parse_args(command))


if __name__ == "__main__":
    unittest.main()
