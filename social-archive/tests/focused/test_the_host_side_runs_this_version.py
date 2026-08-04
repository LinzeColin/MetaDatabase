"""主机那半边跑的必须也是这一版（v0.0.0.7 / T18）。

2026-08-05 实测：容器里的 Core 报 0.0.0.7，而**主机 venv 里装着的是 0.0.0.5**
——落后两个版本。site-packages 里放的是一份拷贝，21 个文件与仓里不同，
account_sync / auth / credentials / platform_payloads 等**六个模块根本不存在**。

而备份、复制、私有库同步、状态发布**四个 timer 全跑在主机 venv 上**。
症状完全静默：systemctl 报 success，备份 PASS，只有去对字段才发现
发布出来的状态页少了一个这一版才有的字段。

判据守两件：部署要检查这件事；以及包元数据的版本别再自己漂。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_package_metadata_version_matches_the_version_file() -> None:
    """pyproject 的 version 一直停在 0.0.0.6，而 VERSION 是 0.0.0.7。

    它决定 `pip install` 记下来的版本号——主机上 `pip show` 因此一直报错的数。
    这种「两个地方各写一份版本」正是漂移的温床。
    """
    declared = re.search(r'^version = "([^"]+)"',
                         (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert declared, "pyproject.toml 里找不到 version"
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert declared.group(1) == expected, (
        f"pyproject 写着 {declared.group(1)}，VERSION 写着 {expected}——两份版本号又漂了"
    )


def test_the_deploy_checks_the_host_venv_is_not_a_stale_copy() -> None:
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "主机 venv" in deploy, "部署脚本不检查主机 venv——四个 timer 可能一直跑旧代码"
    assert "social_archive.__file__" in deploy, "没有去看装着的那份到底是哪个文件"
    assert "pip install -e . --no-deps" in deploy, (
        "发现漂移之后没有修；只报不修的话，下一个人还得自己去敲那行命令"
    )
    assert "social_archive.__version__" in deploy, "没有比对版本号"


def test_install_script_still_uses_an_editable_install() -> None:
    """生产之所以会漂成一份拷贝，就是因为它偏离了 install.sh 写的做法。

    这条判据钉住 install.sh 本身别改成非 editable——一改，
    以后每次同步源码都要重装一次，而没有人会记得。
    """
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert "pip install -e" in install, (
        "install.sh 改成了非 editable 安装——那样 rsync 完源码，主机那半边还是旧的"
    )
