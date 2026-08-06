#!/usr/bin/env python3
"""这次部署到底需不需要重建镜像？

2026-08-07：连着两次，我改的只有一道判据和一个演练（容器从来不跑它们），
而部署脚本照旧走到第 4 步「构建前先看磁盘」，被 4.38G < 5G 拦下中止。
**一次根本不需要构建的部署，卡在了「构建前」的门上。**

于是文档、判据、演练的改动全都推不上去，而它们本来对生产是零风险的。

## 这个问题有精确答案，不需要猜

镜像的输入是**可以穷举的**——就写在 Dockerfile 里：

    COPY pyproject.toml README.md VERSION ./
    COPY src ./src
    COPY apps ./apps
    COPY scripts ./scripts

所以「要不要重建」＝「这些输入里，有没有哪一个和**镜像里那一份**不同」。
镜像里那份可以直接 `docker exec` 出来逐字节比。

**COPY 的清单是从 Dockerfile 现读的，不是我抄一份常量。** 抄一份的话，
哪天有人加了 `COPY deploy ./deploy`，这道判断会安静地漏掉它，
然后说「不用重建」——而那正是它最不该说错的一句话。

## 与 check_production_matches_the_repo.py 的分工

那道门回答「生产跑的是不是仓里这一份」，比的是 scripts/src/apps 下
**特定后缀**的文件。这里不能沿用它：

· 它按后缀过滤（.py/.sh/.js/.css/.html/.json）。改一张图标、一个 .md、
  一个 .txt 都躲得过——**对一道报警的门是小缺口，对一个「可以不构建」的
  决定是真窟窿。** 这里不按后缀过滤，COPY 进去的每个字节都算。
· 它不看 pyproject.toml / VERSION / README.md，而这三个都在 COPY 里。
  改了依赖不重建，装的还是旧依赖。

**「容器从来不跑它」这条规则只有一份**，从那道门 import 过来
（container_never_runs）。抄成两份的那天，一边会说「不用重建」，
另一边会说「在跑旧代码」。

## 不确定一律算「要重建」

ssh 不通、docker exec 失败、Dockerfile 解析不了、一个文件都没数到——
**全都返回「要重建」**。这个方向是安全的：白构建一次只是慢，
而漏构建一次是他打开界面发现改的东西没上去。

（这条是有来历的：这个仓栽在「空默认值被读成没问题」上不止一次，
  最坏一次静默吞掉的是对照基准本身。）

## 它答的不是什么

它比的是**镜像里 /app 的内容**和仓里 COPY 输入是否一致。它不管
base image（python:3.12-slim）有没有更新、apt 包有没有新版本——
那些不是「这次改动要不要重建」的问题。

    python3 scripts/does_this_deploy_need_a_rebuild.py
    退出码 0 = 不用重建（可以跳过构建）；3 = 要重建（含一切不确定）
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# **「容器从来不跑它」这条规则从漂移检查 import，不抄第二份。**
_SPEC = importlib.util.spec_from_file_location(
    "_production_drift_rule", ROOT / "scripts/check_production_matches_the_repo.py")
_RULE_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules["_production_drift_rule"] = _RULE_MODULE
_SPEC.loader.exec_module(_RULE_MODULE)
container_never_runs = _RULE_MODULE.container_never_runs

# 构建期在镜像里生成、仓里没有（或本就不该比）的东西。
# **只排除这些，不排除任何仓里真有的文件。**
IGNORED_PARTS = ("__pycache__", ".pytest_cache", ".ruff_cache")
IGNORED_SUFFIXES = (".pyc", ".pyo")


def _skip(relative: str) -> bool:
    parts = relative.split("/")
    return (any(part in IGNORED_PARTS for part in parts)
            or any(part.endswith(".egg-info") for part in parts)
            or relative.endswith(IGNORED_SUFFIXES))


def image_inputs_from_dockerfile(dockerfile: Path) -> tuple[list[str], str | None]:
    """Dockerfile 里 COPY 进 /app 的源路径清单（**现读，不抄常量**）。

    只认 `COPY <src...> ./` 和 `COPY <src> ./<同名>` 这两种写法。
    遇到看不懂的 COPY（多阶段 --from、改名、通配）就返回错误——
    **看不懂就说看不懂**，由调用方按「要重建」处理。
    """
    sources: list[str] = []
    for raw in dockerfile.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line.upper().startswith("COPY "):
            continue
        if "--from" in line:
            return [], f"看不懂的 COPY（多阶段构建）：{line}"
        tokens = line.split()[1:]
        if len(tokens) < 2:
            return [], f"看不懂的 COPY：{line}"
        destination, given = tokens[-1], tokens[:-1]
        if any("*" in token or "?" in token for token in given):
            return [], f"看不懂的 COPY（带通配符，数不准）：{line}"
        normalised = destination.rstrip("/").removeprefix("./").removeprefix("/app")
        if normalised.strip("/") in ("", "."):
            sources.extend(given)          # COPY a b c ./  → 原名进 /app
            continue
        if len(given) == 1 and normalised.strip("/") == given[0].strip("/"):
            sources.append(given[0])       # COPY src ./src → 同名
            continue
        return [], f"看不懂的 COPY（源和目标不同名，对不上）：{line}"
    if not sources:
        return [], "Dockerfile 里一条 COPY 都没读到——**这不是「没有输入」**"
    return sources, None


def local_hashes(sources: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for source in sources:
        path = ROOT / source
        if path.is_file():
            found[source] = hashlib.sha256(path.read_bytes()).hexdigest()
        elif path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                relative = str(child.relative_to(ROOT))
                if not _skip(relative):
                    found[relative] = hashlib.sha256(child.read_bytes()).hexdigest()
    return found


def image_hashes(host: str, container: str,
                 sources: list[str]) -> tuple[dict[str, str], str | None]:
    """镜像里 /app 那一份——**服务真正执行的就是它**（不是主机上那份）。"""
    listed = " ".join(f"'{source}'" for source in sources)
    inner = (f"cd /app && find {listed} -type f -print0 2>/dev/null "
             "| xargs -0 sha256sum 2>/dev/null")
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
            name = parts[1].strip().removeprefix("./")
            if not _skip(name):
                found[name] = parts[0].strip()
    if not found:
        return {}, "容器里一个文件都没数到——**这不是「一样」**"
    return found, None


def decide(local: dict[str, str], inside: dict[str, str]) -> dict[str, list[str]]:
    """比对结果分三堆。**方向只看「仓 → 镜像」**：镜像里多出来的是构建产物。"""
    differs = sorted(name for name in set(local) & set(inside)
                     if local[name] != inside[name])
    missing = sorted(set(local) - set(inside))
    return {
        "runtime_differs": [n for n in differs if not container_never_runs(n)],
        "missing_from_image": [n for n in missing if not container_never_runs(n)],
        "dev_only_differs": [n for n in differs + missing if container_never_runs(n)],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="这次部署要不要重建镜像")
    parser.add_argument("--host", default="linze-ovh")
    parser.add_argument("--container", default="social-archive-core-api-1")
    args = parser.parse_args()

    def verdict(reason: str, **extra) -> int:
        """**任何不确定都从这里出去，一律「要重建」。**"""
        print(json.dumps({"rebuild_required": True, "why_zh": reason, **extra},
                         ensure_ascii=False))
        return 3

    sources, error = image_inputs_from_dockerfile(ROOT / "Dockerfile")
    if error:
        return verdict(f"读不出镜像输入清单，按「要重建」处理：{error}", undetermined=True)

    local = local_hashes(sources)
    if not local:
        return verdict("本地一个文件都没数到——**这不是「没有改动」**", undetermined=True)

    inside, image_error = image_hashes(args.host, args.container, sources)
    if image_error:
        return verdict(f"读不到镜像里那一份，按「要重建」处理：{image_error}",
                       undetermined=True)

    buckets = decide(local, inside)
    must_build = buckets["runtime_differs"] or buckets["missing_from_image"]
    payload = {
        "rebuild_required": bool(must_build),
        "image_inputs": sources,
        "compared_file_count": {"repo": len(local), "image": len(inside)},
        **buckets,
        "why_zh": (
            "服务真跑的东西和镜像里那份不一致，必须重建。"
            if must_build else
            "COPY 进镜像的每一个文件都和镜像里那份逐字节一致"
            "（开发期脚本除外，容器从来不跑它们）——**这次不用重建**。"),
        "note": ("比的是镜像里 /app 的内容 vs 仓里 COPY 的输入。"
                 "base image 有没有更新、apt 包有没有新版本，不在这道判断里。"),
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 3 if must_build else 0


if __name__ == "__main__":
    sys.exit(main())
