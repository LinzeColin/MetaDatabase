"""CLI Sidecar 必须既写得了产出、又读得了自己的密钥（C-T00-01）。

## 这是 v0.0.0.6「点了同步是 0」的第一处断点

生产实测（2026-08-04，还没修的时候）：

    core-api   uid=10001 gid=10001              → 读 cli_worker_token OK
    cli-tools  uid=10002 gid=999 groups=999,980 → 读 cli_worker_token **拒绝**

原因是**两件事需要两个不同的组，而 compose 只给了一个**：

    写产出  /var/lib/social-archive/vendor-output  10001:980   2770 → socialarchive (980)
    读密钥  /run/secrets/cli_worker_token          10001:10001 0640 → socialarchive-secrets (10001)

`group_add` 里只有 `${SOCIAL_ARCHIVE_HOST_DATA_GID}`，生产 .env 里是 980。
于是密钥读不到。

后果不是「少个功能」：`/health` 照样 200，业务路由一律 401，
job 层终态 failed 而 sync_run 仍是 scanning、last_error_code 为空
——界面永远「同步中」。**又一次没有任何地方说得出为什么。**

更糟的是旧注释写着「Production must set this to `id -g socialarchive`」，
那正是 980，等于把这个故障写进了操作指引。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = (ROOT / "compose.yaml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
PREPARE = (ROOT / "scripts/prepare_systemd_host.sh").read_text(encoding="utf-8")


def _group_add_block() -> str:
    match = re.search(r"group_add:\n((?:\s*-\s*\"[^\"]+\"\n)+)", COMPOSE)
    assert match, "compose.yaml 里找不到 group_add"
    return match.group(1)


def test_sidecar_gets_both_the_data_group_and_the_secrets_group() -> None:
    """一个 group_add 条目是不够的——两件事需要两个组。"""
    block = _group_add_block()
    assert "SOCIAL_ARCHIVE_HOST_DATA_GID" in block, "少了写产出用的数据组"
    assert "SOCIAL_ARCHIVE_HOST_SECRETS_GID" in block, (
        "少了读 /run/secrets/ 用的密钥组——这正是 C-T00-01："
        "/health 200 而业务路由全 401，界面永远「同步中」"
    )
    assert len(re.findall(r"-\s*\"\$\{", block)) >= 2, f"group_add 只有一个条目：{block!r}"


def test_the_two_groups_have_different_defaults() -> None:
    """默认值必须不同。配成一样，必然有一边坏掉。"""
    block = _group_add_block()
    data = re.search(r"SOCIAL_ARCHIVE_HOST_DATA_GID:-(\d+)", block)
    secrets = re.search(r"SOCIAL_ARCHIVE_HOST_SECRETS_GID:-(\d+)", block)
    assert data and secrets, "两个 GID 都要有默认值"
    assert data.group(1) != secrets.group(1), (
        f"数据组与密钥组默认值相同({data.group(1)})——"
        "写产出要 socialarchive、读密钥要 socialarchive-secrets，是两个组"
    )
    # 实测到的生产值
    assert data.group(1) == "980", "数据组默认值应为生产实测的 socialarchive gid"
    assert secrets.group(1) == "10001", "密钥组默认值应为生产实测的 socialarchive-secrets gid"


def test_the_old_comment_no_longer_tells_you_to_set_the_broken_value() -> None:
    """旧注释把故障写进了操作指引，不能留着。"""
    assert "Production must set this to `id -g socialarchive`" not in COMPOSE, (
        "那句话让人把 group_add 配成 980（数据组），于是密钥读不了"
    )


def test_env_example_declares_both_and_they_differ() -> None:
    data = re.search(r"^SOCIAL_ARCHIVE_HOST_DATA_GID=(\d+)", ENV_EXAMPLE, re.M)
    secrets = re.search(r"^SOCIAL_ARCHIVE_HOST_SECRETS_GID=(\d+)", ENV_EXAMPLE, re.M)
    assert data, ".env.example 少了 SOCIAL_ARCHIVE_HOST_DATA_GID"
    assert secrets, ".env.example 少了 SOCIAL_ARCHIVE_HOST_SECRETS_GID"
    assert data.group(1) != secrets.group(1), "示例里两个 gid 一样，会直接把故障配置抄进生产"


def test_host_prep_refuses_to_proceed_when_the_secrets_gid_is_missing_or_equal() -> None:
    """预检必须在 --dry-run 阶段就拦住，而不是等上线之后 401。"""
    assert "SOCIAL_ARCHIVE_HOST_SECRETS_GID" in PREPARE, "预检根本不看密钥组"
    assert "C-T00-01" in PREPARE, "预检里没有指回这个故障的编号，日后没人知道为什么要查"
    # 必须有"两者不能相等"这条
    assert re.search(
        r'SOCIAL_ARCHIVE_HOST_SECRETS_GID\)"\s*!=\s*"\$\(env_value SOCIAL_ARCHIVE_HOST_DATA_GID', PREPARE
    ), "预检没有拦住「两个组配成同一个 gid」"


@pytest.mark.parametrize("secret", ["cli_worker_token", "instagram_session"])
def test_every_secret_the_sidecar_mounts_is_declared(secret: str) -> None:
    """挂进来却读不了，和没挂一样——先确保它确实是挂给 sidecar 的。"""
    sidecar = COMPOSE[COMPOSE.index("cli-tools:"):]
    assert secret in sidecar, f"{secret} 没有挂给 cli-tools"
