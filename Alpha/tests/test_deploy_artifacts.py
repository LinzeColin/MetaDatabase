"""ALPHA-LIVE-040:部署工件卫生——五单元齐全、模板零秘密、失败关闭默认。"""

from pathlib import Path

DEPLOY = Path("deploy")


def test_systemd_units_ledger():
    units = {p.name for p in (DEPLOY / "systemd").glob("*.service")}
    assert units == {
        "alpha-opend.service", "alpha-trading-worker.service",
        "alpha-notify-worker.service", "alpha-supervisor.service",
        "alpha-control-page.service", "alpha-rejudge.service",
        "alpha-activate.service",
    }
    # oneshot 台账:复判必须声明无激活权限;切换器必须声明自己是激活唯一通道
    oneshot_marks = {"alpha-rejudge.service": "无激活权限",
                     "alpha-activate.service": "激活唯一通道"}
    for p in (DEPLOY / "systemd").glob("*.service"):
        text = p.read_text()
        assert "EnvironmentFile=/opt/alpha/env" in text, p.name
        if "Type=oneshot" in text:
            assert p.name in oneshot_marks and oneshot_marks[p.name] in text, p.name
        else:
            assert "Restart=always" in text, p.name
    timers = {p.name for p in (DEPLOY / "systemd").glob("*.timer")}
    assert timers == {"alpha-rejudge.timer"}
    paths = {p.name for p in (DEPLOY / "systemd").glob("*.path")}
    assert paths == {"alpha-activate.path"}


def test_env_template_contains_no_real_secrets():
    text = (DEPLOY / "env.template").read_text()
    assert "LIVE_TRADING_ENABLED=0" in text          # 默认失败关闭
    for line in text.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            _, _, value = line.partition("=")
            # 允许:空、占位符、公开常量(主机名/端口/路径/公开收件地址)
            assert (
                value == "" or "<REQUIRED" in value
                or value.startswith(("smtp.", "imap.", "127.0.0.1", "/opt/alpha", "0", "11111", "587"))
                or value == "linzezhang35@gmail.com"
                or value == "FUTUAU"   # 公开 SDK 枚举常量(开户主体),非秘密
            ), f"env.template 疑似真值: {line}"


def test_setup_script_hardens_and_never_enables_live():
    text = (DEPLOY / "setup.sh").read_text()
    for required in ("ufw default deny incoming", "fail2ban", "unattended-upgrades",
                     "install -m 600", "sparse-checkout set Alpha"):
        assert required in text
    assert "LIVE_TRADING_ENABLED=1" not in text       # 部署脚本永不开实盘


def test_worker_entrypoints_importable_and_build():
    """systemd 单元指向的入口必须真实存在且可装配(冒烟,不跑长驻循环)。"""
    import os
    import tempfile

    from backend.app.workers import main_notify, main_supervisor, main_trading
    from backend.app.control_page import main as control_main

    with tempfile.TemporaryDirectory() as tmp:
        old_db = os.environ.get("ALPHA_DATABASE_URL")
        old_ks = os.environ.get("ALPHA_KILL_SWITCH_PATH")
        os.environ["ALPHA_DATABASE_URL"] = f"sqlite:///{tmp}/smoke.sqlite"
        os.environ["ALPHA_KILL_SWITCH_PATH"] = f"{tmp}/KILL_SWITCH"
        try:
            worker = main_trading.build_worker()
            assert worker is not None
            summary = worker._run_cycle()  # noqa: SLF001 - 冒烟:空转周期诚实报告未接通
            assert summary["status"] == "BLOCKED_ON_OPEND"
            sup = main_supervisor.build_supervisor()
            assert sup is not None
            app = control_main.build_app()
            assert app is not None
            assert main_notify.WORKER_NAME == "notify-worker"
        finally:
            for key, val in (("ALPHA_DATABASE_URL", old_db), ("ALPHA_KILL_SWITCH_PATH", old_ks)):
                if val is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = val
