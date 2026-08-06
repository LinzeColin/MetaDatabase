#!/usr/bin/env python3
"""生产上跑的，是不是仓里这一份（v0.0.0.7 / T18）。

## 为什么需要它

`/opt/social-archive` **不是 git 检出**——代码是 `deploy_to_production.sh`
用 rsync 送上去的。于是那台机器上**没有 `git status` 可问**：
没有任何东西能回答「生产现在跑的和仓里一样吗」。

2026-08-05 我自己就往那儿 scp 过一个脚本。事后想确认没弄脏，
才发现要确认这件事得临时敲四条命令去拼——**而这正是出事那天最先要问的问题**。

部署脚本第 8 道门只逐字节核了**扩展包**那一个文件。其余一百多个源文件，
从来没有任何东西核过。

## 要比的是**三份**，不是两份

    仓 ←→ 主机 `/opt/social-archive` ←→ **镜像里的 `/app`**

第三份是 2026-08-05 才弄清楚的：`/app` 是**烤进镜像的**，不是主机目录的
绑定挂载（只有 `/run/secrets/*` 是）。所以改主机上的脚本，容器里那份
纹丝不动，直到镜像重建。当时就撞上了：往主机放了个修好的脚本，
在容器里跑，跑的还是旧的。

运维手册早就用另一种说法警告过同一件事：「`systemctl restart` 不会重建镜像」。
**只比前两份会得出一个安心但不成立的结论**——主机同步对了，服务可能还在跑上一版。

## 分类，要紧程度完全不同

  · **只在生产有** —— 最要紧。**那是没人知道从哪来的代码，正在生产上跑。**
    手工改的、scp 上去的、旧版本删剩的，都会落在这一类。
  · **镜像比仓旧** —— 服务正在执行的不是你以为的那一版。
  · 主机内容不同 —— 要看是不是只差注释。差逻辑就是真漂移。
  · 只在本地有 —— 通常只是「还没部署」，最轻。

**别把它们混成一个数报出来。** 「有 5 处不同」听着像一件事，
而其中一处是「生产上有个来路不明的文件」，另外四处是「新写的还没发」。

## 边界

· **只读。** ssh 过去只跑 find / sha256sum / cat，不写、不改、不重启。
· 只比 `scripts/` 与 `src/` 下的 `.py`/`.sh`。运行数据、密钥、`runtime/`
  一概不碰——那些本来就该两边不一样。
· 注释差异会单独标出来，但**不当成「相同」**：注释也是交接的一部分。
· 镜像那一份只比「仓里有而镜像里旧/没有」，**不报「镜像里多出来的」**：
  镜像里本来就有仓里没有的东西（依赖、构建产物）。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# **apps/ 一开始不在这里，而它才是 Owner 看得见的那一半。**
#
# 2026-08-05 改了一处 PWA 的样式，正要部署时才想起来这道检查只比
# scripts/ 与 src/——也就是说**界面代码漂了它一句话都不会说**。
# 一道叫「生产跑的是不是仓里这一份」的门，漏掉用户唯一看得见的那部分，
# 是它能犯的最难堪的错。
COMPARED = ("scripts", "src", "apps")
SUFFIXES = ("*.py", "*.sh", "*.js", "*.css", "*.html", "*.json")


def inert_in_the_image(name: str) -> bool:
    """这个文件进了镜像，但**改它不会改变镜像做的任何事**吗？

    名字原来叫 `container_never_runs`，2026-08-07 改掉了：那个名字是错的，
    而错的名字会把人引到错的豁免上。`build_extension_package.py` 容器同样
    从来不跑（它在构建期跑），但它**决定了镜像里那个扩展包长什么样**，
    所以它绝不能豁免。要问的不是「容器跑不跑它」，是「改了它，镜像做的事
    会不会变」。

    **开发期脚本和服务跑的东西，分开说。**

    判据和演练（scripts/check_*.py、scripts/*_drill.py）会被打进镜像
    （Dockerfile 里 `COPY scripts ./scripts`），但**容器从来不跑它们**——
    ENTRYPOINT 是 container-entrypoint.sh，构建期只用 build_extension_package.py。

    2026-08-07：我连着两次只改了一道判据和一个演练，而漂移检查报的是
    「服务执行的不是你以为的那一版，要重建镜像」——**听起来像生产在跑旧代码**，
    而实际上他那边跑的东西一个字节没变。这个仓一整天都在修同一种病：
    **指错原因的告警，比不告警更费人**。

    所以照报（差异就是差异，不许藏），但分开归类，并且不因为它单独失败。

    **放在模块级是因为它有第二个调用方**（does_this_deploy_need_a_rebuild.py，
    它拿这条规则决定要不要真去构建镜像）。这种规则一旦被抄成两份，
    两份就会各自漂——而漂的那天，一边说「不用重建」另一边说「在跑旧代码」。

    **名单只列豁免项，所以新加的东西默认不豁免**——方向是安全的那一侧。
    往里加名字要有测量支撑，而那个测量已经落成判据
    （tests/focused/test_production_drift_check.py 里那条：豁免的每一个脚本，
    都不许被 Dockerfile / ENTRYPOINT / compose / src / apps 引用，
    也不许被任何 systemd 单元的 ExecStart 调用）。
    """
    base = name.rsplit("/", 1)[-1]
    return name.startswith("scripts/") and (
        base.startswith("check_") or base.endswith("_drill.py")
        or base in {"run_all_drills.py", "drill_extension_dir.py", "final_verify.py",
                    # 下面这三个都是**从我这台机器跑、ssh 过去操作主机**的，
                    # 镜像里那份是 `COPY scripts` 顺带带进去的死文件。
                    # 2026-08-07 实测：ENTRYPOINT 是 `exec "$@"`，src/、apps/、
                    # Dockerfile、compose、systemd 单元里一处引用都没有。
                    "does_this_deploy_need_a_rebuild.py",
                    "deploy_to_production.sh",
                    "reclaim_our_superseded_images.sh"})


def _local_hashes() -> dict[str, str]:
    import hashlib
    found: dict[str, str] = {}
    for directory in COMPARED:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for pattern in SUFFIXES:
            for path in base.rglob(pattern):
                if path.is_file():
                    found[str(path.relative_to(ROOT))] = hashlib.sha256(
                        path.read_bytes()).hexdigest()
    return found


def _remote_hashes(host: str, remote_dir: str) -> tuple[dict[str, str], str | None]:
    patterns = " -o ".join(f"-name '{pattern}'" for pattern in SUFFIXES)
    command = (
        f"cd {remote_dir} && sudo find {' '.join(COMPARED)} -type f \\( {patterns} \\) "
        "-print0 2>/dev/null | sudo xargs -0 sha256sum 2>/dev/null"
    )
    done = subprocess.run(["ssh", "-o", "ConnectTimeout=20", host, command],
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return {}, (done.stderr.strip() or "ssh 失败")[:200]
    found: dict[str, str] = {}
    for line in done.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            found[parts[1].strip()] = parts[0].strip()
    if not found:
        return {}, "远端一个文件都没数到——**这不是「一样」**，多半是路径或权限不对"
    return found, None


def _container_hashes(host: str, container: str) -> tuple[dict[str, str], str | None]:
    """容器里 `/app` 那一份——**服务真正在执行的就是它**。

    2026-08-05 才弄清楚：`/app` 是**烤进镜像的**，不是 `/opt/social-archive`
    的绑定挂载（只有 `/run/secrets/*` 是绑定挂载）。所以

        改主机上的脚本 → 容器里那份纹丝不动，直到镜像重建。

    这件事运维手册早就用另一种说法警告过：「`systemctl restart` 不会重建镜像」。
    **同一个坑的另一面**：主机同步对了，服务可能还在跑上一版。

    于是「生产和仓一样吗」其实有三份要比：仓、主机、**镜像里那份**。
    只比前两份会得出一个安心但不成立的结论。
    """
    patterns = " -o ".join(f"-name '{pattern}'" for pattern in SUFFIXES)
    inner = (f"cd /app && find {' '.join(COMPARED)} -type f \\( {patterns} \\) "
             "-print0 2>/dev/null | xargs -0 sha256sum 2>/dev/null")
    done = subprocess.run(
        ["ssh", "-o", "ConnectTimeout=20", host,
         f"sudo docker exec {container} sh -lc \"{inner}\""],
        capture_output=True, text=True, check=False)
    if done.returncode != 0:
        return {}, (done.stderr.strip() or "docker exec 失败")[:200]
    found: dict[str, str] = {}
    for line in done.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            found[parts[1].strip()] = parts[0].strip()
    if not found:
        return {}, "容器里一个文件都没数到——**这不是「一样」**"
    return found, None


def _without_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines()
                     if not line.strip().startswith("#") and line.strip())


def classify(local: dict[str, str], remote: dict[str, str]) -> dict[str, list[str]]:
    """把差异分成三类。**分类本身就是这个工具的全部价值**，所以它单独成函数。

    「有 5 处不同」听着像一件事，而其中一处可能是「生产上有个来路不明的文件」，
    另外四处是「新写的还没发」。**混成一个数报出来，等于什么都没说。**

    单独成函数还有一个理由：判据可以直接喂它两个字典看它怎么分，
    而不必真去连一台机器。grep 源码守不住分类逻辑。
    """
    return {
        "only_on_production": sorted(set(remote) - set(local)),
        "only_local": sorted(set(local) - set(remote)),
        "differing": sorted(name for name in set(local) & set(remote)
                            if local[name] != remote[name]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="核对生产上跑的是不是仓里这一份")
    parser.add_argument("--host", default="linze-ovh")
    parser.add_argument("--remote-dir", default="/opt/social-archive")
    parser.add_argument("--container", default="social-archive-core-api-1",
                        help="顺带核一下**容器里那份**（服务真正执行的）；给空串跳过")
    parser.add_argument("--explain-differences", action="store_true",
                        help="对内容不同的文件，再取一次远端内容，区分「只差注释」与「差逻辑」")
    args = parser.parse_args()

    local = _local_hashes()
    if not local:
        print(json.dumps({"status": "FAIL", "error_code": "NOTHING_TO_COMPARE",
                          "message_zh": "本地一个文件都没数到——**这不是通过**。"},
                         ensure_ascii=False))
        return 4
    remote, error = _remote_hashes(args.host, args.remote_dir)
    if error:
        print(json.dumps({"status": "FAIL", "error_code": "REMOTE_UNREADABLE",
                          "message_zh": error}, ensure_ascii=False))
        return 4

    # **第三份：镜像里那一份。** 主机同步对了不等于服务在跑它——
    # /app 是烤进镜像的，改主机不重建镜像的话，容器里纹丝不动。
    container_stale: list[str] = []
    container_note = "没查（--container 给了空串）"
    if args.container:
        inside, container_error = _container_hashes(args.host, args.container)
        if container_error:
            container_note = f"查不了：{container_error}"
            container_stale = ["<查不了，见 container_note>"]
        else:
            container_stale = sorted(
                name for name in set(local) & set(inside) if local[name] != inside[name]
            ) + sorted(set(local) - set(inside))
            container_note = (
                f"镜像里 {len(inside)} 个文件；**它才是服务在执行的那一份**"
                if not container_stale else
                "**镜像比仓旧——主机同步过了，但没重建镜像。** "
                "运维手册那句「systemctl restart 不会重建镜像」说的就是这个。"
                "跑 scripts/deploy_to_production.sh（或生产上的 update.sh）才会重建。")

    buckets = classify(local, remote)
    only_on_production = buckets["only_on_production"]
    only_local = buckets["only_local"]
    differing = buckets["differing"]

    comment_only: list[str] = []
    logic_differs: list[str] = list(differing)
    if args.explain_differences and differing:
        logic_differs = []
        for name in differing:
            done = subprocess.run(
                ["ssh", "-o", "ConnectTimeout=20", args.host,
                 f"sudo cat {args.remote_dir}/{name}"],
                capture_output=True, text=True, check=False)
            if done.returncode != 0:
                logic_differs.append(name)
                continue
            here = _without_comments((ROOT / name).read_text(encoding="utf-8"))
            there = _without_comments(done.stdout)
            (comment_only if here == there else logic_differs).append(name)

    dev_only_differs = [name for name in logic_differs if inert_in_the_image(name)]
    logic_differs = [name for name in logic_differs if not inert_in_the_image(name)]
    if container_stale:
        container_stale = [name for name in container_stale if not inert_in_the_image(name)]

    # **「只在生产有」单独作为失败条件。** 那是没人说得清来路的代码，正在跑。
    status = "FAIL" if only_on_production or logic_differs or container_stale else "PASS"
    print(json.dumps({
        "status": status,
        "host": args.host,
        "remote_dir": args.remote_dir,
        "compared_file_count": {"local": len(local), "production": len(remote)},
        "only_on_production": only_on_production,
        "only_on_production_means": (
            "**没人知道从哪来的代码，正在生产上跑**——手工改的、scp 上去的、"
            "或旧版本删剩的。这一类最要紧。" if only_on_production else "无"),
        "logic_differs": logic_differs,
        "comment_only": comment_only,
        # 判据和演练：进了镜像，但容器从来不跑它们。差异照报，不算服务在跑旧代码。
        "dev_only_differs": dev_only_differs,
        "dev_only_means": (
            "判据/演练与仓里不一致。它们被 COPY 进镜像，但 ENTRYPOINT 不跑它们——"
            "**服务的行为不受影响**，下次发布会一起带上。"
            if dev_only_differs else "无"),
        "only_local_not_deployed_yet": only_local,
        "container_is_running_older_code": container_stale,
        "container_note": container_note,
        # **这句话要从常量生成，不能手写。**
        # 手写那版说「只比 scripts/ 与 src/ 下的 .py/.sh」，而范围早就加上了
        # apps/ 与前端后缀——一道专门查「说的和实际是不是一回事」的门，
        # 自己的自述先陈了。
        "note": (f"只比 {'/、'.join(COMPARED)} 下的 "
                 f"{'/'.join(s.lstrip('*') for s in SUFFIXES)}；"
                 "runtime/、密钥、数据本来就该两边不同。"),
    }, ensure_ascii=False))
    return 0 if status == "PASS" else 4


if __name__ == "__main__":
    sys.exit(main())
