"""挂进容器的密钥，容器必须读得到（v0.0.0.7 / C-T00-01 家族）。

这条不变量此前**只存在于一句注释里**——scripts/prepare_systemd_host.sh:205：

    /run/secrets/*   10001:10001 0640 → 要 socialarchive-secrets

没有任何一行代码去落实它。生产上那些 0640 是不知哪一次手敲出来的，
而 instagram_session 被漏掉了，一直是 0600。

后果（2026-08-04 生产实测）：cli-tools 跑在 uid 10002 / gid 10001，
0600 owner=10001 一点权限都不给，于是

    POST /v1/connectors/instagram/run
    → [Errno 13] Permission denied: '/run/secrets/instagram_session'

**不管有没有配 session，Instagram 从来就没能工作过。**

而这个原因之前也是看不见的：它被 `CLI Sidecar 调用失败：HTTP 422` 盖住了
（见 test_sidecar_reason_is_not_thrown_away.py）。两个缺陷叠在一起，
一个让它坏掉，另一个让它说不出为什么。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def compose_mounted_secrets() -> set[str]:
    """服务块里引用的密钥名。

    顶层 `secrets:` 定义块写的是 `name: {file: …}`，不带前导 `- `，
    所以这条正则天然只会命中服务块里的引用。
    """
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    return set(re.findall(r"^\s+-\s+(?:source:\s*)?([a-z0-9_]+)\s*$", text, re.M))


def test_there_is_something_that_actually_applies_the_invariant() -> None:
    """注释不是实现。"""
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert "chmod 640" in install, (
        "没有任何一行代码给挂进容器的密钥授组读权限——"
        "那条不变量就只是 prepare_systemd_host.sh 里的一句注释"
    )
    assert "chown 10001:10001" in install, "没有把属组设成 socialarchive-secrets(10001)"


def test_the_list_comes_from_compose_not_a_second_copy() -> None:
    """名单必须从 compose.yaml 读。抄一份必然漂开——instagram_session 就是这么被漏掉的。"""
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    # **切到那段赋值为止。** 第一版切 900 个字符，一路切进后面另一个
    # Python heredoc，那里出现的 'social_archive_api_token' 让判据误报。
    # 判据自己钉错范围，和它要防的「第二份清单」是同一种病。
    block = install.split("mounted=", 1)[1].split("PYMOUNTED\n)", 1)[0]
    assert "compose.yaml" in block, "挂载名单不是从 compose.yaml 读的"
    for name in ("instagram_session", "cli_worker_token"):
        assert f'"{name}"' not in block and f"'{name}'" not in block, (
            f"{name} 被硬编码进了名单——那就是第二份会漂开的清单"
        )


def test_every_mounted_secret_is_also_created_by_the_installer() -> None:
    """compose 对缺文件是硬错：少一个，docker compose up 直接起不来。"""
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    missing = [name for name in compose_mounted_secrets() if name not in install]
    assert not missing, f"compose 要挂这些密钥，而安装脚本不创建它们：{sorted(missing)}"


def test_instagram_session_is_among_them() -> None:
    """回归钉：它就是被漏掉的那一个。"""
    assert "instagram_session" in compose_mounted_secrets()
