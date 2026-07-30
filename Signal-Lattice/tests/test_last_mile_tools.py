from __future__ import annotations

import json
import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class LastMileToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.env = os.environ.copy()
        cls.env["PYTHONPATH"] = str(cls.root / "src")

    def run_script(self, script: str, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [os.sys.executable, str(self.root / "scripts" / script), *args],
            cwd=cwd or self.root,
            env=self.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )

    def test_dual_plane_semantic_patch_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / ".github/workflows").mkdir(parents=True)
            (repo / "AGENTS.md").write_text("rules\n")
            workflow = textwrap.dedent('''
                name: dual
                jobs:
                  test:
                    steps:
                      - run: |
                          python3 - <<'PY'
                          registered = {
                            "Alpha",
                            "Serenity-Alipay",
                          }
                          print("PASS: 2 governance projects + ABD specialized task-pack workflow classified")
                          PY
                          python3 "$DUAL_PLANE_TOOL" --root . --projects \\
                            Alpha Serenity-Alipay \\
                            --exceptions ABD
                ''').lstrip()
            path = repo / ".github/workflows/dual-plane.yml"
            path.write_text(workflow)
            result = self.run_script("apply_meta_dual_plane.py", "--repo", str(repo), "--apply")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            changed = path.read_text()
            self.assertIn('"Signal-Lattice"', changed)
            self.assertIn("PASS: 3 governance projects", changed)
            second = self.run_script("apply_meta_dual_plane.py", "--repo", str(repo), "--apply")
            self.assertEqual(second.returncode, 0)
            self.assertFalse(json.loads(second.stdout)["changed"])

    def test_status_registration_patches_actual_python_registry(self):
        with tempfile.TemporaryDirectory() as temp:
            status = Path(temp) / "status"
            tests = status / "collector/tests"
            tests.mkdir(parents=True)
            collector = status / "collector/collect.py"
            collector.write_text(textwrap.dedent('''
                import re
                SYSTEMD_SERVICE_PATTERN = re.compile(r"(alpha|eei)[-.@]")
                PROJECTS = [
                    {"name": "Home", "url": "https://home.linzezhang.com", "parts": ["前台"],
                     "host": "OVH", "db": "无", "store": "无", "deploy": "host", "backup": "yes",
                     "agent": "无", "notify": "无", "owns": {"systemd": ["home-"]}},
                ]
                PLATFORM = [{"name":"x","role":"x","owns":{"systemd":["x-"]},"heal":"x"}]
                STAGES = [("code","代码"),("ci","CI"),("deploy","部署"),("run","运行"),("entry","入口"),("data","数据"),("backup","备份"),("monitor","监控"),("heal","自愈")]
                ''').lstrip())
            (tests / "test_software_registry.py").write_text(textwrap.dedent('''
                import os,sys,unittest
                sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                import collect as C
                class T(unittest.TestCase):
                    def test_signal(self):
                        p=next(x for x in C.PROJECTS if x["name"]=="Signal Lattice")
                        self.assertEqual(p["owns"]["systemd"],["signal-lattice-"])
                        self.assertIsNotNone(C.SYSTEMD_SERVICE_PATTERN.match("signal-lattice-api.service"))
                if __name__=="__main__":unittest.main()
                ''').lstrip())
            result = self.run_script("register_status.py", "--status-root", str(Path(temp)), "--apply")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["test"]["state"], "PASS")
            second = self.run_script("register_status.py", "--status-root", str(Path(temp)), "--apply")
            self.assertEqual(second.returncode, 0)
            self.assertFalse(json.loads(second.stdout)["changed"])

    def test_land_project_never_overwrites_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source"
            source.mkdir()
            (source / "a.txt").write_text("source")
            repo = root / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            first = self.run_script("land_project.py", "--source", str(source), "--target-repo", str(repo), "--apply")
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            target = repo / "Signal-Lattice/a.txt"
            self.assertEqual(target.read_text(), "source")
            target.write_text("target-newer")
            blocked = self.run_script("land_project.py", "--source", str(source), "--target-repo", str(repo), "--apply")
            self.assertEqual(blocked.returncode, 2)
            self.assertEqual(target.read_text(), "target-newer")
            self.assertEqual(json.loads(blocked.stdout)["counts"]["conflict"], 1)

    def test_context_capture_is_read_only_and_redacts_remote_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            subprocess.run(["git", "remote", "add", "origin", "https://user:secret@github.com/LinzeColin/MetaDatabase.git"], cwd=repo, check=True)
            (repo / "AGENTS.md").write_text("rules")
            out = Path(temp) / "capture.json"
            result = self.run_script("context_capture.py", "--output", str(out), "--target-repo", str(repo))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(out.read_text())
            self.assertNotIn("user:secret", json.dumps(payload))
            self.assertFalse(payload["production_write_actions_performed"])
            self.assertFalse(payload["secrets_collected"])


if __name__ == "__main__":
    unittest.main()
