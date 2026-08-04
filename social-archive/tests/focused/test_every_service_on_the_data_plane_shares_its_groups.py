"""同一个数据面上的服务，权限必须一致（v0.0.0.7 / T16 / C-T00-01 家族）。

2026-08-05 生产实测，**第二次**因为这件事断线：

    -rw-rw---- 1 10001         socialarchive  social-archive.sqlite3
    -rw-rw---- 1 socialarchive socialarchive  social-archive.sqlite3-shm
    -rw-rw---- 1 socialarchive socialarchive  social-archive.sqlite3-wal

主库属主是 10001（容器建的），而 -wal/-shm 属主是 **987**（宿主
socialarchive 账号建的——status 定时任务每 5 分钟以它的身份写库）。
模式 0660、组 980，而 Core 是 uid 10001 / gid 10001：**属主不对，组也不对**。
SQLite 报 `unable to open database file`，所有要鉴权的路由 500，
core-worker 直接退出。

它一直"能用"，只是因为碰巧总是容器先建那两个文件。
**哪一次宿主任务先建，Core 就被锁在外面。** 今天早些时候那次"一次性的 500"
就是它，当时被下一次重建掩盖了，我误记成磁盘压力。

cli-tools 一直有 group_add，core-api / core-worker 一直没有——
同一个数据面，两套权限，迟早对不上。

## 这个文件用 yaml 解析，不手搓

第一版手搓：从 `group_add:` 往下数带 `-` 的行——一路数进了后面的
`secrets:` 列表，于是「应当正好两个」读出 14 个，判据对着正确的配置转红。
**手搓 YAML 是这一天里我第三次在自己的判据上栽跟头。**
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ROOT / "compose.yaml"

# 挂了共享数据面（bind 到 /var/lib/social-archive）的服务。
DATA_PLANE_SERVICES = ("core-api", "core-worker", "cli-tools")


def _services() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]


def test_the_data_plane_services_are_the_ones_that_mount_it() -> None:
    """名单不是我拍的：谁 bind 了共享的宿主路径，谁就在这个数据面上。

    漏掉一个服务，这套判据就守不住它——所以先证明名单是完整的。

    **看的是冒号左边（宿主那一侧）。** 第一版看容器内路径
    `/var/lib/social-archive`，于是漏掉了 cli-tools——它把同一块宿主目录
    挂到了 `/work/output`。共享的是宿主上那块盘，不是容器里的路径名。
    """
    services = _services()
    mounting = {
        name for name, spec in services.items()
        if any("SOCIAL_ARCHIVE_" in str(volume).split(":", 1)[0] and "HOST_PATH" in str(volume).split(":", 1)[0]
               for volume in (spec.get("volumes") or []))
    }
    assert mounting == set(DATA_PLANE_SERVICES), (
        f"挂了数据面的服务是 {sorted(mounting)}，而判据盯的是 {sorted(DATA_PLANE_SERVICES)}"
    )


def test_every_data_plane_service_joins_both_groups() -> None:
    services = _services()
    for name in DATA_PLANE_SERVICES:
        groups = [str(item) for item in (services[name].get("group_add") or [])]
        joined = " ".join(groups)
        assert "SOCIAL_ARCHIVE_HOST_DATA_GID" in joined, (
            f"{name} 没加入宿主数据组——它只能读写自己建的文件，"
            "宿主任务先建 -wal/-shm 就会把它锁在外面"
        )
        assert "SOCIAL_ARCHIVE_HOST_SECRETS_GID" in joined, f"{name} 没加入密钥组"
        assert len(groups) == 2, f"{name} 的 group_add 有 {len(groups)} 项，应当正好两项"


def test_the_two_gids_are_not_the_same_variable() -> None:
    """写产出要 socialarchive(980)，读密钥要 socialarchive-secrets(10001)。

    配成同一个必然有一边坏掉——这条是 C-T00-01 的原始教训。
    """
    services = _services()
    for name in DATA_PLANE_SERVICES:
        groups = [str(item) for item in (services[name].get("group_add") or [])]
        assert len(set(groups)) == 2, f"{name} 的两个组配成了同一个值：{groups}"
