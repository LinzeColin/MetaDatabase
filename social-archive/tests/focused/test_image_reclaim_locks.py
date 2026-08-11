"""守住「收掉我们自己上一个版本的镜像」那四道自锁（2026-08-07）。

**这段脚本会真的 `docker rmi`，而那台机器上还跑着别人的项目**
（memory-atlas / gatus / coolify）。删错一个，别人的回滚点就没了。
所以它不能只靠读一遍就上线。

这里给它一个**假 docker**：喂一份镜像/容器清单，把它调用的每一次 `rmi`
记下来，然后逐条证明——

  ① 只动 social-archive/ 开头的     ② 跳过当前版本
  ③ 跳过 rollback / rollback-candidate  ④ 跳过任何被容器引用的镜像 ID

**外加一条正例：该收的那个真的被收了。** 只验反例是红的不够——一个什么都
不删的脚本能让上面四条全过，而它等于没做。
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/reclaim_our_superseded_images.sh"

_SUDO_STUB = '#!/bin/sh\nexec "$@"\n'

_DOCKER_STUB = r'''#!/usr/bin/env python3
"""假 docker：只认这段脚本真正用到的那几条子命令。"""
import os, sys

def table(name):
    out = {}
    for entry in os.environ.get(name, "").split(";"):
        if entry.strip():
            key, _, value = entry.partition("=")
            out[key] = value
    return out

images = table("FAKE_IMAGES")          # ref -> image id
containers = table("FAKE_CONTAINERS")  # container id -> image id
argv = sys.argv[1:]

if argv[:1] == ["images"]:
    for ref in images:
        print(ref)
elif argv[:2] == ["ps", "-aq"]:
    for cid in containers:
        print(cid)
elif argv[:1] == ["inspect"]:
    for cid in argv[3:]:
        if cid not in containers:
            sys.exit(1)
        print(containers[cid])
elif argv[:2] == ["image", "inspect"]:
    ref = argv[-1]
    if ref not in images:
        sys.exit(1)
    print(images[ref])
elif argv[:1] == ["rmi"]:
    with open(os.environ["RMI_LOG"], "a", encoding="utf-8") as log:
        log.write(argv[1] + "\n")
else:
    sys.stderr.write("假 docker 不认识：%s\n" % " ".join(argv))
    sys.exit(2)
'''


def _run(tmp_path: Path, images: dict[str, str], containers: dict[str, str],
         current: str) -> list[str]:
    binaries = tmp_path / "bin"
    binaries.mkdir(exist_ok=True)
    (binaries / "sudo").write_text(_SUDO_STUB, encoding="utf-8")
    (binaries / "docker").write_text(_DOCKER_STUB, encoding="utf-8")
    for name in ("sudo", "docker"):
        (binaries / name).chmod(0o755)

    log = tmp_path / "rmi.log"
    log.write_text("", encoding="utf-8")
    environment = dict(os.environ)
    environment.update({
        "PATH": f"{binaries}:{environment['PATH']}",
        "FAKE_IMAGES": ";".join(f"{k}={v}" for k, v in images.items()),
        "FAKE_CONTAINERS": ";".join(f"{k}={v}" for k, v in containers.items()),
        "RMI_LOG": str(log),
    })
    done = subprocess.run(["bash", str(SCRIPT), current],
                          capture_output=True, text=True, env=environment, check=False)
    assert done.returncode == 0, done.stderr
    return [line for line in log.read_text(encoding="utf-8").splitlines() if line]


# 2026-08-07 生产上真实的那一份（照抄 `docker images` 的输出）。
PRODUCTION = {
    "social-archive/core:0.0.0.22": "sha256:a9ecb33ede10",
    "social-archive/core:rollback": "sha256:304ada83d01d",
    "social-archive/cli-tools:0.0.0.22": "sha256:c8e6fa598b79",
    "social-archive/core:0.0.0.21": "sha256:365be6663c0c",
    "social-archive/cli-tools:0.0.0.21": "sha256:5467b2737f4a",
    # 同机别的项目——**一个都不许碰**
    "memory-atlas/app:latest": "sha256:memoryatlas01",
    "gatus/gatus:v5": "sha256:gatus000001",
    "ghcr.io/coollabsio/coolify:4": "sha256:coolify00001",
}
RUNNING = {
    "social-archive-core-api-1": "sha256:a9ecb33ede10",
    "social-archive-core-worker-1": "sha256:a9ecb33ede10",
    "social-archive-cli-tools-1": "sha256:c8e6fa598b79",
    "memory-atlas-web-1": "sha256:memoryatlas01",
}


def test_it_actually_reclaims_the_superseded_version(tmp_path: Path) -> None:
    """**正例。** 该收的两个（上一个版本、没有容器在用）真的被收了。

    这条排在最前面：没有它，下面四条自锁的判据全是空的。
    """
    removed = _run(tmp_path, PRODUCTION, RUNNING, current="0.0.0.22")
    assert sorted(removed) == ["social-archive/cli-tools:0.0.0.21",
                               "social-archive/core:0.0.0.21"]


def test_it_never_touches_another_project(tmp_path: Path) -> None:
    """① 这台机器还跑着 memory-atlas / gatus / coolify。"""
    removed = _run(tmp_path, PRODUCTION, RUNNING, current="0.0.0.22")
    for ref in removed:
        assert ref.startswith("social-archive/"), f"**动了别的项目的镜像：{ref}**"


def test_it_never_removes_the_current_version(tmp_path: Path) -> None:
    """② 删掉正在跑的这一版 = 服务下一次重启就起不来。"""
    removed = _run(tmp_path, PRODUCTION, RUNNING, current="0.0.0.22")
    assert "social-archive/core:0.0.0.22" not in removed
    assert "social-archive/cli-tools:0.0.0.22" not in removed


def test_the_current_version_is_kept_even_with_no_container_on_it(tmp_path: Path) -> None:
    """② 单独承压：**当前版本没有任何容器在用时，也不许删。**

    2026-08-07 做变异测试才发现：把「跳过当前版本」整条删掉，上面那条判据
    **七条全过**——因为当前版本恰好被容器引用着，是第④道锁挡下的。
    ②③④ 三道锁挡的是同一批镜像时，拆掉一道没人看得出来。

    这个场景是真会发生的：回收跑在**构建之前**，上一次部署如果在
    `compose up` 之前断掉，当前版本的镜像就躺在盘上而没有任何容器引用它。
    """
    orphaned = {
        "social-archive/core:0.0.0.22": "sha256:freshbuild01",   # 建好了，还没起
        "social-archive/core:0.0.0.21": "sha256:365be6663c0c",
    }
    removed = _run(tmp_path, orphaned, containers={}, current="0.0.0.22")
    assert "social-archive/core:0.0.0.22" not in removed, (
        "**当前版本被收掉了**——没有容器在用不等于不需要它")
    assert removed == ["social-archive/core:0.0.0.21"], (
        "同时要证明它没有退化成「一个都不收」")


def test_it_never_removes_the_rollback_point(tmp_path: Path) -> None:
    """③ 回滚点没了，出事就退不回去。"""
    images = dict(PRODUCTION)
    images["social-archive/core:rollback-candidate"] = "sha256:candidate01"
    removed = _run(tmp_path, images, RUNNING, current="0.0.0.22")
    assert "social-archive/core:rollback" not in removed
    assert "social-archive/core:rollback-candidate" not in removed


def test_a_rollback_tag_on_the_other_image_is_kept_too(tmp_path: Path) -> None:
    """③ 单独承压：**保留名单只 inspect `core:rollback`，不认 cli-tools 的。**

    2026-08-07 变异测试查出来的：把「按 tag 名跳过 rollback」整条删掉，
    上面那条判据照样全绿——因为 `core:rollback` 的**镜像 ID** 已经在第④道锁的
    保留名单里，两道锁挡的是同一个东西。

    但它们并不总是同一个东西：保留名单是**逐个 tag 手写 inspect** 出来的
    （只写了 core 的 rollback / rollback-candidate）。cli-tools 今天没有
    rollback tag，哪天有了，第④道锁不会知道，**只有按名字那一条拦得住**。
    """
    images = dict(PRODUCTION)
    images["social-archive/cli-tools:rollback"] = "sha256:clirollback1"
    removed = _run(tmp_path, images, RUNNING, current="0.0.0.22")
    assert "social-archive/cli-tools:rollback" not in removed, (
        "**cli-tools 的回滚点被收掉了**——保留名单里没有它，按名字那道锁是唯一防线")


def test_a_tag_sharing_the_rollback_image_id_is_kept(tmp_path: Path) -> None:
    """③ 之二：**tag 名字不一样，底下可能是同一个镜像。**

    只按 tag 名躲开 rollback 是不够的——回滚点常常同时挂着一个版本号 tag，
    把那个版本号 tag 删掉就等于解绑了回滚点。所以要按**镜像 ID** 拦。
    """
    images = dict(PRODUCTION)
    images["social-archive/core:0.0.0.20"] = "sha256:304ada83d01d"   # == rollback
    removed = _run(tmp_path, images, RUNNING, current="0.0.0.22")
    assert "social-archive/core:0.0.0.20" not in removed, (
        "**它和回滚点是同一个镜像**，删这个 tag 等于把回滚点解绑了")


def test_an_image_used_by_a_stopped_container_is_kept(tmp_path: Path) -> None:
    """④ `docker ps` 看不见已停止的容器，而它们照样引用着镜像。"""
    stopped = dict(RUNNING)
    stopped["social-archive-oneshot-migration"] = "sha256:365be6663c0c"  # 0.0.0.21
    removed = _run(tmp_path, PRODUCTION, stopped, current="0.0.0.22")
    assert "social-archive/core:0.0.0.21" not in removed, (
        "有个**已停止的**容器还引用着它")
    assert "social-archive/cli-tools:0.0.0.21" in removed, (
        "拦对了一个不代表另一个也该拦——这条同时证明它没有变成「一个都不收」")


def test_nothing_to_reclaim_is_not_an_error(tmp_path: Path) -> None:
    """全是当前版本时收不到东西，**这不是失败**——磁盘门在后面会重新量。"""
    only_current = {"social-archive/core:0.0.0.22": "sha256:a9ecb33ede10"}
    assert _run(tmp_path, only_current, RUNNING, current="0.0.0.22") == []
