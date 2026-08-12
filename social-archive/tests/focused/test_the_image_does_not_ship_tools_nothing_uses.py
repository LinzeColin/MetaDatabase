"""镜像里不许装没人用的东西（v0.0.0.20）。

2026-08-06 部署的磁盘门反复卡在 5G。这台机器还跑着别人的项目
（memory-atlas / gatus / coolify），**我们唯一能动的只有自己的镜像**——
所以先去看自己装了什么用不上的。

查出来 core 镜像装着 ffmpeg，而 core 根本调不到它：
能调用 ffmpeg 的是 gallery-dl / yt-dlp，**这两个都不在那个镜像里**
（媒体那条路在 sidecars/cli-tools 里跑）。对着正在跑的镜像实测：

    ffmpeg -> /usr/bin/ffmpeg        gallery-dl -> 没有
    ffprobe -> /usr/bin/ffprobe      yt-dlp     -> 没有

`apt-get -s autoremove --purge ffmpeg` 要拆掉 **192 个包**。

这条判据把规矩写下来：**core 的 Dockerfile 里装的每个外部命令，
要么被代码调用，要么写清它为什么在（健康检查、加密、证书）。**
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "Dockerfile"
SIDECAR = ROOT / "sidecars/cli-tools/Dockerfile"

# 装了但代码里不会直接出现的，每条写清它为什么在
JUSTIFIED = {
    "ca-certificates": "出站 HTTPS 要根证书",
    "curl": "HEALTHCHECK 那一行用它",
    "git": "scripts/vendor_sync.py 与 check_docs_point_at_things_that_exist.py 会调",
    "age": "credentials.py / encryption.py 直接以子进程调用",
}


def _installed(dockerfile: Path) -> set[str]:
    text = dockerfile.read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines()
                     if not line.lstrip().startswith("#"))
    found = re.search(r"apt-get install[^\n]*--no-install-recommends([^\n\\]*)", code)
    assert found, f"{dockerfile.name} 里找不到 apt-get install 那一行"
    return {word for word in found.group(1).split() if word and not word.startswith("-")}


def test_core_does_not_install_ffmpeg() -> None:
    """**核心镜像不装 ffmpeg。** 它在这里是纯死重，而磁盘门反复卡在 5G。"""
    packages = _installed(DOCKERFILE)
    assert "ffmpeg" not in packages, (
        "core 镜像又装上 ffmpeg 了——能调它的 gallery-dl / yt-dlp 不在这个镜像里，"
        "它拖着 192 个包的依赖树，而部署的磁盘门一直卡在 5G"
    )


def test_every_binary_in_the_core_image_is_justified() -> None:
    """装的每一样都要说得出为什么。"""
    packages = _installed(DOCKERFILE)
    unexplained = sorted(packages - set(JUSTIFIED))
    assert not unexplained, (
        f"core 镜像装了这些而没写为什么：{unexplained}。"
        "要么代码真的调用它，要么写进 JUSTIFIED 并说清理由——"
        "**说不出理由的依赖，是下一个 192 个包**"
    )


def test_the_media_sidecar_still_has_ffmpeg() -> None:
    """**反过来也要成立。** 媒体那条路真的需要它，别一起删了。

    只验「core 没有」是不够的：一个两边都删掉的改动同样能过上面那条，
    而那会让媒体归档静默地坏掉。
    """
    if not SIDECAR.is_file():
        return
    assert "ffmpeg" in SIDECAR.read_text(encoding="utf-8"), (
        "cli-tools 那个镜像里也没有 ffmpeg 了——媒体归档会坏"
    )
