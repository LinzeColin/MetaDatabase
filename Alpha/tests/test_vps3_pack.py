"""I3:VPS-3 影子盘部署包卫生——单元白名单、加固、无升级链、env 模板零秘密、安装脚本契约、CI 契约。

全部是静态检查,离线,不执行安装脚本。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PACK = Path("deploy/vps3")
UNITS = PACK / "systemd"
INSTALL = PACK / "install.sh"
CI = Path("../.github/workflows/alpha-ci.yml")

WHITELIST = {
    "alpha.slice",
    "alpha-trading-worker.service", "alpha-notify-worker.service",
    "alpha-supervisor.service", "alpha-control-page.service",
    "alpha-equity-snapshot.service", "alpha-equity-snapshot.timer",
    "alpha-preflight.service", "alpha-preflight.timer",
    "alpha-backup.service", "alpha-backup.timer",
    "alpha-digest.service", "alpha-digest.timer",
    "alpha-alert@.service",
}
LONG_LIVED = {"alpha-trading-worker.service", "alpha-notify-worker.service",
              "alpha-supervisor.service", "alpha-control-page.service"}
ONESHOT = {"alpha-equity-snapshot.service", "alpha-preflight.service",
           "alpha-backup.service", "alpha-digest.service"}
COMMON_HARDENING = [
    "User=alpha", "Group=alpha", "WorkingDirectory=/opt/alpha/app/Alpha",
    "EnvironmentFile=/opt/alpha/env", "Environment=PYTHONDONTWRITEBYTECODE=1",
    "StateDirectory=alpha", "StateDirectoryMode=0700", "Slice=alpha.slice", "Nice=10",
    "TasksMax=64", "NoNewPrivileges=yes", "ProtectSystem=strict", "ProtectHome=yes",
    "PrivateTmp=yes", "PrivateDevices=yes", "ReadWritePaths=/var/lib/alpha",
    "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
]


def _services() -> list[Path]:
    return sorted(UNITS.glob("*.service"))


def _lines(path: Path) -> list[str]:
    return [ln.strip() for ln in path.read_text().splitlines()]


def test_unit_whitelist_excludes_upgrade_chain():
    names = {p.name for p in UNITS.iterdir()}
    assert names == WHITELIST
    for n in names:
        assert not n.startswith(("alpha-opend", "alpha-activate", "alpha-rejudge")), n


def test_no_forbidden_references():
    forbidden = ["activate_micro_live", "daily_rejudge", "ACTIVATE_REQUEST", "alpha-opend",
                 "sudo", "LIVE_TRADING_ENABLED=1", "postgresql", "ufw", "fail2ban",
                 "timedatectl", "reset --hard", "apt-get upgrade"]
    for p in PACK.rglob("*"):
        if p.is_file():
            text = p.read_text()
            for word in forbidden:
                assert word not in text, f"{p} 含禁用字样 {word}"


def test_every_service_hardened():
    for p in _services():
        lines = _lines(p)
        for want in COMMON_HARDENING:
            assert want in lines, f"{p.name} 缺 {want}"
        assert any(ln.startswith("MemoryMax=") for ln in lines), p.name
        text = p.read_text()
        if p.name in LONG_LIVED:
            assert "Restart=always" in lines, p.name
        else:
            assert "Type=oneshot" in lines, p.name
            assert "永不下单" in text, p.name
        # 日志只进 journald:不许有落文件的配置
        assert not re.search(r"^(StandardOutput|StandardError)=(file|append|truncate)", text, re.M), p.name
    for name in ONESHOT:
        text = (UNITS / name).read_text()
        assert "OnFailure=alpha-alert@%n.service" in text, name
        assert re.search(r"^ExecStartPost=-?/opt/alpha/venv/bin/python scripts/notify_unit_failure\.py --ok %n$",
                         text, re.M), name
    # 失败自告警钩子本身不能再挂 OnFailure/--ok,否则自己触发自己
    alert = (UNITS / "alpha-alert@.service").read_text()
    assert "OnFailure" not in alert and "--ok" not in alert
    assert "ExecStart=/opt/alpha/venv/bin/python scripts/notify_unit_failure.py %i" in alert


def test_worker_watchdog_and_no_opend_dependency():
    lines = _lines(UNITS / "alpha-trading-worker.service")
    for want in ("Type=notify", "NotifyAccess=main", "WatchdogSec=300", "TimeoutStartSec=300",
                 "MemoryMax=512M", "Restart=always", "RestartSec=10"):
        assert want in lines, want
    for p in _services():
        for ln in _lines(p):
            if ln.startswith(("Requires=", "After=", "Wants=", "BindsTo=", "PartOf=")):
                assert "opend" not in ln and "postgres" not in ln, f"{p.name}: {ln}"


def test_slice_limits():
    lines = _lines(UNITS / "alpha.slice")
    assert "MemoryMax=1G" in lines and "CPUQuota=100%" in lines
    for p in _services():
        assert "Slice=alpha.slice" in _lines(p), p.name
        assert any(ln.startswith("MemoryMax=") for ln in _lines(p)), p.name


def test_timers_schedule():
    want = {
        "alpha-equity-snapshot.timer": "OnUnitActiveSec=15min",
        "alpha-preflight.timer": "OnCalendar=Mon..Fri 13:15:00 UTC",
        "alpha-backup.timer": "OnCalendar=*-*-* 21:10:00 UTC",
        "alpha-digest.timer": "OnCalendar=*-*-* 21:30:00 UTC",
    }
    for name, line in want.items():
        lines = _lines(UNITS / name)
        assert line in lines, name
        assert "Persistent=true" in lines, name
        assert "WantedBy=timers.target" in lines, name


def _env_pairs() -> dict[str, str]:
    pairs = {}
    for ln in (PACK / "env.template").read_text().splitlines():
        if ln.strip() and not ln.lstrip().startswith("#"):
            k, _, v = ln.partition("=")
            pairs[k] = v
    return pairs


def test_env_template_shadow_safe():
    from backend.app.workers.shadow_cycle import FORBIDDEN_ENV

    pairs = _env_pairs()
    for k, v in {
        "ALPHA_MODE": "SHADOW", "LIVE_TRADING_ENABLED": "0",
        "ALPHA_DATABASE_URL": "sqlite:////var/lib/alpha/alpha.sqlite",
        "ALPHA_STRATEGY_CONFIG": "configs/strategies/s1_gem_plus.yaml",
        "ALPHA_SUPERVISOR_SUDO_RESTART": "0",
    }.items():
        assert pairs.get(k) == v, k
    for k in pairs:
        assert k not in FORBIDDEN_ENV, k
        assert not k.startswith(("ALPHA_IMAP_", "OPEND_", "MOOMOO_")), k
    public_constants = {"SHADOW", "0", "14", "configs/strategies/s1_gem_plus.yaml"}
    for k, v in pairs.items():
        assert (v == "" or "<REQUIRED" in v or v in public_constants
                or v.startswith(("/var/lib/alpha", "sqlite:////var/lib/alpha", "127.0.0.1:"))), \
            f"env.template 疑似真值: {k}={v}"
        assert "@" not in v, f"env.template 不许出现邮箱明文: {k}"
    # 行尾注释会被 systemd 当成值的一部分
    for ln in (PACK / "env.template").read_text().splitlines():
        if "=" in ln and not ln.lstrip().startswith("#"):
            assert " #" not in ln, ln


def test_install_script_contract():
    text = INSTALL.read_text()
    for needle in ("set -euo pipefail", "--no-cache-dir", "checkout --detach",
                   "status --porcelain --untracked-files=no", "install -m 600 -o root -g root",
                   "alpha_doctor.py --check-env", "ss -ltnH", "/api/overview",
                   "sparse-checkout set Alpha", "--sparse", "DEPLOYED_SHA",
                   "python3.12-venv", "tomllib", "pip check", "mode_code", "SHADOW"):
        assert needle in text, needle
    # 必填参数校验
    assert '缺少必填参数 --repo' in text and '缺少必填参数 --sha' in text
    assert "[0-9a-f]{40}" in text
    # 清理包外 alpha-* 单元
    assert "包外单元" in text and "systemctl disable --now" in text
    # env 只在不存在时生成;仍有 <REQUIRED 就不启用并退出 2
    assert "绝不覆盖" in text and "exit 2" in text and "<REQUIRED" in text
    # 不放宽的事:不升级系统、不改别的、不强制重置
    assert "apt-get install -y --no-install-recommends python3.12-venv" in text
    assert "apt-get upgrade" not in text and "reset --hard" not in text
    # 写入目标只限 /opt/alpha、/var/lib/alpha、/etc/systemd/system/alpha*(及变量指向它们)
    allowed = ("/opt/alpha", "/var/lib/alpha", "/etc/systemd/system")
    for m in re.finditer(r"(?<![A-Za-z0-9_$\"'{}./-])(/(?:opt|var|etc|usr|srv|home|root|tmp)/[A-Za-z0-9_./@-]*)", text):
        path = m.group(1)
        if path.startswith(("/usr/bin/env", "/usr/sbin/nologin", "/dev/")):
            continue
        assert path.startswith(allowed), f"install.sh 出现允许范围外的路径 {path}"
    assert "/tmp" not in text


@pytest.mark.parametrize("script", [INSTALL])
def test_install_script_bash_syntax(script):
    r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    if shutil.which("shellcheck") is None:
        pytest.skip("本机没有 shellcheck:只校验了 bash -n 语法,shellcheck 由 CI 跑")
    r = subprocess.run(["shellcheck", "-S", "warning", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_ci_workflow_contract():
    import yaml

    text = CI.read_text()
    doc = yaml.safe_load(text)
    assert doc["name"] == "Alpha CI"
    triggers = doc[True] if True in doc else doc["on"]      # PyYAML 把 on 读成布尔 True
    paths = ["Alpha/**", ".github/workflows/alpha-ci.yml"]
    assert triggers["push"]["branches"] == ["main"] and triggers["push"]["paths"] == paths
    assert triggers["pull_request"]["paths"] == paths
    assert "workflow_dispatch" in triggers
    assert doc["permissions"] == {"contents": "read"}
    assert doc["concurrency"] == {"group": "alpha-ci-${{ github.ref }}", "cancel-in-progress": True}
    # action 的 SHA 钉法与仓内其它专属 CI(pfi-tests)一致
    pfi = Path("../.github/workflows/pfi-tests.yml").read_text()
    for action in ("actions/checkout", "actions/setup-python"):
        mine = re.search(rf"{action}@([0-9a-f]{{40}}) # (v\S+)", text)
        theirs = re.search(rf"{action}@([0-9a-f]{{40}}) # (v\S+)", pfi)
        assert mine and theirs and mine.groups() == theirs.groups(), action
    steps = doc["jobs"]["test"]["steps"]
    setup = next(s for s in steps if "setup-python" in s.get("uses", ""))
    assert setup["with"]["python-version"] == "3.12"
    pytest_step = next(s for s in steps if "pytest" in s.get("run", ""))
    assert pytest_step["working-directory"] == "Alpha"
    assert pytest_step["run"] == "python -m pytest -q -p no:cacheprovider"
    lint = next(s for s in steps if "shellcheck" in s.get("run", ""))
    assert "bash -n Alpha/deploy/vps3/install.sh" in lint["run"]
    assert "shellcheck -S warning Alpha/deploy/vps3/install.sh" in lint["run"]
