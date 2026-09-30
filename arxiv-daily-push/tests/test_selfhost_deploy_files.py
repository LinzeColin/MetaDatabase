"""自托管部署件的静态合规检查：每一条对应任务书里的一项硬要求，防止以后有人改回去。"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
D = ROOT / "deploy" / "selfhost"


def read(name: str) -> str:
    return (D / name).read_text(encoding="utf-8")


def env_value(text: str, key: str) -> str:
    m = re.search(rf"^{key}=(.*?)(?:\s+#.*)?$", text, re.M)
    assert m, f"adp.env 缺 {key}"
    return m.group(1).strip().strip("'\"")


class DockerfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.df = read("Dockerfile")

    def test_runs_as_non_root_with_fixed_uid(self) -> None:
        users = re.findall(r"^USER\s+(\S+)", self.df, re.M)
        self.assertTrue(users and users[-1] not in ("root", "0", "0:0"), users)
        self.assertEqual(users[-1], "10001:10001")
        self.assertIn("adduser -u 10001", self.df)

    def test_only_listens_inside_container_and_has_no_shell_entrypoint(self) -> None:
        self.assertIn("EXPOSE 8080", self.df)
        self.assertRegex(self.df, r'CMD \["node", "/app/server\.mjs"\]')

    def test_no_third_party_dependencies_are_installed(self) -> None:
        self.assertNotRegex(self.df, r"npm (i|install|ci)|yarn|pnpm|pip install")

    def test_copies_the_single_shipped_worker_not_a_fork(self) -> None:
        self.assertIn("COPY cloudflare/worker_cloud.js /app/vendor/worker_cloud.js", self.df)
        self.assertIn("COPY cloudflare/schema_cloud.sql /app/schema_cloud.sql", self.df)


class DeployConfigTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = read("adp.env")

    def test_memory_limit_is_256m_read_only_and_caps_dropped(self) -> None:
        self.assertEqual(env_value(self.env, "MEMORY"), "256m")
        extra = env_value(self.env, "RUN_EXTRA_ARGS")
        for flag in ("--read-only", "--cap-drop ALL", "--user 10001:10001", "-v /var/lib/adp:/data"):
            self.assertIn(flag, extra)

    def test_traffic_only_through_traefik_no_published_ports(self) -> None:
        self.assertNotRegex(self.env, r"(^|\s)-p\s|--publish")
        self.assertNotIn("--network host", self.env)
        self.assertEqual(env_value(self.env, "DOCKER_NETWORK"), "coolify")
        self.assertEqual(env_value(self.env, "DOMAIN"), "adp.linzezhang.com")
        run_block = read("adp-pull-deploy.sh").split("docker run -d", 1)[1].split('"${largs[@]}"')[0]
        self.assertNotRegex(run_block, r"(^|\s)(-p|--publish|-P)(\s|=)", "候选容器不许发布端口，流量只走 Traefik")

    def test_health_check_and_source_are_public_and_credential_free(self) -> None:
        self.assertEqual(env_value(self.env, "HEALTH_PATH"), "/healthz")
        self.assertTrue(env_value(self.env, "REPO_URL").startswith("https://github.com/LinzeColin/MetaDatabase"))
        self.assertNotRegex(self.env, r"(?i)token|secret|password|api[_-]?key")

    def test_pull_deploy_keeps_switch_only_after_health_and_rollback_on_failure(self) -> None:
        s = read("adp-pull-deploy.sh")
        order = [s.index(k) for k in ("wait_healthy \"$CAND\"", "docker network connect", "docker stop -t 15", "postcheck \"$(sha256_of")]
        self.assertEqual(order, sorted(order), "顺序必须是：健康 -> 接入 Traefik 网络 -> 停旧 -> 回测")
        self.assertIn("fail()", s)
        self.assertIn("docker start \"$c\"", s)   # 失败把旧容器拉起来
        self.assertIn("REQUIRE_DIR", s)
        self.assertRegex(s, r"REPO_URL 必须是不带凭据的 https")

    def test_one_shot_job_container_does_not_masquerade_as_the_live_container(self) -> None:
        s = read("adp-daily-run.sh")
        self.assertIn('--label "linze.pull.app=$APP-job"', s)


class SystemdUnitTests(unittest.TestCase):
    def test_daily_unit_has_onfailure_limits_and_total_timeout(self) -> None:
        u = read("adp-daily.service")
        self.assertIn("OnFailure=adp-failure@%n.service", u)
        for k in ("TimeoutStartSec=3h", "MemoryMax=", "CPUQuota=", "TasksMax="):
            self.assertIn(k, u)
        self.assertNotIn("RuntimeMaxSec", u.replace("RuntimeMaxSec 对 oneshot 无效", ""))   # oneshot 下无效，不能当成「总时长上限」
        r = read("adp-daily-run.sh")
        for k in ("--memory \"$MEMORY\"", "--memory-swap", "--cpus 1", "--pids-limit", "--cap-drop ALL", "--read-only", "timeout --signal=TERM"):
            self.assertIn(k, r)

    def test_backfill_unit_is_also_guarded(self) -> None:
        u = read("adp-backfill.service")
        self.assertIn("OnFailure=adp-failure@%n.service", u)
        self.assertIn("TimeoutStartSec=", u)

    def test_timers_use_utc_slots_matching_the_old_cron(self) -> None:
        self.assertIn("OnCalendar=*-*-* 20:30:00 UTC", read("adp-daily.timer"))
        self.assertIn("Persistent=true", read("adp-daily.timer"))
        b = read("adp-backfill.timer")
        self.assertIn("02:30:00 UTC", b); self.assertIn("08:30:00 UTC", b)

    def test_failure_recorder_writes_a_durable_line(self) -> None:
        s = read("adp-record-failure.sh")
        self.assertIn("failures.log", s); self.assertIn("logger -p user.err", s)

    @unittest.skipUnless(shutil.which("systemd-analyze"), "需要 systemd-analyze")
    def test_calendar_expressions_parse_and_units_verify(self) -> None:
        for cal in ("*-*-* 20:30:00 UTC", "*-*-* 02:30:00 UTC", "*-*-* 08:30:00 UTC", "*:5/10"):
            p = subprocess.run(["systemd-analyze", "calendar", cal], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
        files = [str(D / n) for n in ("adp-daily.service", "adp-daily.timer", "adp-backfill.service", "adp-backfill.timer", "adp-web-pull.service", "adp-web-pull.timer", "adp-failure@.service")]
        p = subprocess.run(["systemd-analyze", "verify", "--man=no", *files], capture_output=True, text=True)
        # 「命令不存在」是因为脚本还没装到 /usr/local/bin，与 unit 本身无关；其余任何告警都算失败
        bad = [l for l in (p.stdout + p.stderr).splitlines() if l.strip() and "is not executable" not in l]
        self.assertEqual(bad, [], "\n".join(bad))


class ScriptSyntaxTests(unittest.TestCase):
    def test_bash_scripts_parse(self) -> None:
        for n in ("adp-pull-deploy.sh", "adp-daily-run.sh", "adp-record-failure.sh", "adp-import-d1.sh", "install.sh"):
            p = subprocess.run(["bash", "-n", str(D / n)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, f"{n}: {p.stderr}")

    def test_scripts_are_executable(self) -> None:
        for n in ("adp-pull-deploy.sh", "adp-daily-run.sh", "adp-record-failure.sh", "adp-import-d1.sh", "install.sh", "migrate_from_d1.py"):
            self.assertTrue((D / n).stat().st_mode & 0o111, n)

    def test_install_declares_every_unit_and_script_in_the_directory(self) -> None:
        inst = read("install.sh")
        for p in D.iterdir():
            if p.suffix in (".sh", ".service", ".timer", ".env") or p.name == "adp-failure@.service":
                if p.name == "install.sh":
                    continue
                self.assertIn(f'["{p.name}"]', inst, f"install.sh 没安装 {p.name}")


class NoLaunchdNoCloudflareInNewPathTests(unittest.TestCase):
    def test_no_launchd_anywhere_in_selfhost(self) -> None:
        for p in D.rglob("*"):
            if p.is_file() and "tests" not in p.parts:
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotRegex(t, r"(?i)launchctl|LaunchAgent|\.plist\b|StartCalendarInterval", str(p))

    def test_launchd_plists_for_the_old_mac_tunnel_are_gone(self) -> None:
        self.assertFalse((ROOT / "deploy" / "cloudflare" / "launchd").exists())

    def test_runtime_path_makes_no_cloudflare_calls(self) -> None:
        pat = re.compile(r"wrangler|workers\.dev|api\.cloudflare\.com|CLOUDFLARE_API|cloudflared|r2\.cloudflarestorage|d1_databases|env\.RAW")
        for p in list(D.glob("*.sh")) + list(D.glob("*.service")) + list(D.glob("*.timer")) + list(D.glob("*.env")) + [D / "Dockerfile"]:
            code = "\n".join(l for l in p.read_text(encoding="utf-8").splitlines() if not l.lstrip().startswith("#"))
            self.assertIsNone(pat.search(code), p.name)

    def test_migration_script_is_offline_stdlib_only(self) -> None:
        """迁移脚本只读导出文件：不能 import 任何网络 / 子进程模块（文档字符串里提到 wrangler 只是告诉人怎么导出）。"""
        src = (D / "migrate_from_d1.py").read_text(encoding="utf-8")
        imports = set(re.findall(r"^(?:import|from)\s+([A-Za-z0-9_\.]+)", src, re.M))
        self.assertFalse(imports & {"urllib", "urllib.request", "http", "http.client", "socket", "requests", "subprocess", "ssl"}, imports)

    def test_no_secrets_or_dotenv_committed(self) -> None:
        self.assertFalse(list(D.rglob(".env")))
        for p in D.rglob("*"):
            if p.is_file():
                t = p.read_text(encoding="utf-8", errors="ignore")
                self.assertNotRegex(t, r"(?i)(ghp_|github_pat_|sk-[A-Za-z0-9]{20}|BEGIN (RSA |OPENSSH )?PRIVATE KEY)", str(p))


if __name__ == "__main__":
    unittest.main()
