#!/usr/bin/env python3
"""代码读了、而任何部署面都设不了的配置项（v0.0.0.7）。

## 第五种「建好了没接上」

前四道门看的是：Python 符号没人引用、HTTP 接口没有界面调用、
storage 键写了没人读、扩展消息只有一头。第五种它们都看不见：

    代码 os.getenv("SOCIAL_ARCHIVE_XXX") 读一个变量
      → .env.example 没有它
      → compose.yaml 没有它
      → 部署脚本、systemd 单元、文档全都没有它

于是**没有任何一条文档化的路径能把它设上**。运行时它永远是 None，
分支永远走「未配置」那一支。功能在代码上完整，在部署上不存在。

## 本轮实际抓到的

    SOCIAL_ARCHIVE_REDDIT_USERNAME       registry.py 读它
    SOCIAL_ARCHIVE_REDDIT_USER_AGENT     registry.py 读它
    SOCIAL_ARCHIVE_X_USER_ID             registry.py 读它
    SOCIAL_ARCHIVE_INSTAGRAM_USERNAME    registry.py 读它

这四个是 X / Reddit / Instagram 账号扫描的**身份**参数。缺了它，
连接器一律返回 blocked_environment。也就是说：Owner 把该做的都做对了
（部署、登录、连接账号），这三个平台的服务端同步仍然一条都取不到，
**而没有任何文档告诉他还差什么**——正是 INV-ZERO-BARRIER 要防的那种
看不见也修不了的门槛。

## 判据

扫 src/ 下所有 `os.getenv("SOCIAL_ARCHIVE_…")` / `os.environ.get(…)`，
比对 .env.example、compose*.yaml、deploy/、scripts/、docs/ 的全文。
一处都没出现的报出来。

## 豁免

写进 NO_SETTING_NEEDED，每条说清为什么不需要能设——通常是
「有默认值且默认值就是对的」。**「暂时没人用」不是理由**：那说明该删。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# **不能只认 getenv("…")。** registry.py 里的密钥文件是通过一个小工厂读的：
#     self._secret("SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE")
#     @staticmethod def _secret(env_name): return lambda: read_secret(os.getenv(env_name))
# 变量名到了 getenv 那一行已经不是字面量了。只认 getenv 会**恰好漏掉密钥类**
# ——也就是最需要被登记的那一类。所以认 src/ 里出现的任何 SOCIAL_ARCHIVE_* 字面量。
READ = re.compile(r'"(SOCIAL_ARCHIVE_[A-Z0-9_]+)"')

SURFACE_FILES = (".env.example",)
SURFACE_DIRS = ("deploy", "scripts", "docs")
SURFACE_GLOBS = ("compose*.yaml", "compose*.yml")

# 不需要能设的。每条写清为什么——「暂时没人用」不算理由。
NO_SETTING_NEEDED: dict[str, str] = {
    "SOCIAL_ARCHIVE_ACCOUNT_SYNC_INTERVAL_MINUTES": "同步节奏调优旋钮，默认值即产品行为；要改是运维的事，不是部署必需项。",
    "SOCIAL_ARCHIVE_ACCOUNT_SYNC_MAX_ITEMS": "单次同步条目上限（安全阀），默认值即产品行为。",
    "SOCIAL_ARCHIVE_ACCOUNT_SYNC_PAGE_SIZE": "翻页大小，默认值即产品行为。",
    "SOCIAL_ARCHIVE_EXTENSION_PACKAGE": "扩展 zip 的路径，默认指向仓内 dist/；只有换打包路径时才需要覆盖。",
    "SOCIAL_ARCHIVE_PRIVATE_DATABASE_ROOT": "**故意读不到。** Private-Database 只走 API，禁止挂载或克隆本地副本；这一项存在是为了在有人设了它时能显式拒绝。",
}


def settable_lines(text: str) -> str:
    """只留下**能把值设上**的行，把「也在读它」的行剔掉。

    第一版把整个 scripts/ 当部署面，于是 REDDIT_USERNAME / X_USER_ID
    被判为「有地方设」——因为 platform_canary.py 里有一句
    `os.getenv('SOCIAL_ARCHIVE_REDDIT_USERNAME')`。**那是另一个读的人，
    不是一条能设它的路。** 和上一道门里「验收脚本不算客户端」同一个错，
    本轮第四次射程写错。

    scripts/ 不能整个排除：install.sh 确实会写出 .env，那是真正的设置面。
    所以按行判定，不按目录判定。
    """
    keep = []
    for line in text.splitlines():
        if "getenv(" in line or "environ.get(" in line or "environ[" in line:
            continue
        keep.append(line)
    return "\n".join(keep)


def surface_text() -> str:
    chunks: list[str] = []
    for name in SURFACE_FILES:
        path = ROOT / name
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    for pattern in SURFACE_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    for folder in SURFACE_DIRS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.name == Path(__file__).name:
                continue
            if path.suffix in {".sh", ".md", ".service", ".timer", ".yaml", ".yml", ".conf", ".py", ""}:
                try:
                    chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
                except OSError:
                    continue
    return settable_lines("\n".join(chunks))


def main() -> int:
    if not SRC.is_dir():
        print("找不到 src/，跳过（这是跳过，不是通过）")
        return 0

    read_at: dict[str, set[str]] = {}
    for path in sorted(SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name in READ.findall(text):
            read_at.setdefault(name, set()).add(str(path.relative_to(ROOT)))

    blob = surface_text()
    unsettable = sorted(
        name for name in read_at
        if name not in blob and name not in NO_SETTING_NEEDED
    )

    print(f"src/ 读取 {len(read_at)} 个 SOCIAL_ARCHIVE_* 配置项；"
          f"另有 {len(NO_SETTING_NEEDED)} 项已登记为无需可设")
    if not unsettable:
        print("每一项都至少有一处能设它的地方。")
        return 0

    print(f"\n**任何部署面都设不了的 {len(unsettable)} 项** —— "
          "运行时永远是 None，分支永远走「未配置」那一支：")
    for name in unsettable:
        print(f"  {name}")
        for where in sorted(read_at[name]):
            print(f"        读于 {where}")
    print("\n写进 .env.example（或 compose / 部署脚本 / 文档），"
          "或写进 NO_SETTING_NEEDED 并说清为什么不需要能设。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
