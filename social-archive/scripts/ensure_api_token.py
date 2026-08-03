#!/usr/bin/env python3
"""确保长期 API 令牌存在（幂等）。

## 它是从哪来的

v0.0.0.7 / T03 删除一次性配对码链路时，`scripts/generate_pairing_code.py` 整个脚本
本来要一起删——但它其实干了**两件事**：

  1. 生成一次性配对码（十分钟过期、要用户手抄）→ 已废止，删
  2. 顺带把长期 API 令牌 `social_archive_api_token` 建出来（不存在时才建）→ **还要**

只看名字会以为它整个都是配对码的事，删掉之后 `install.sh` / `start.sh` 就再没有
任何地方创建 API 令牌了，Core 起来直接没有凭据。所以第 2 件事被单独留在这里。

## `atomic_secret` 为什么这么写

不是"写个文件"这么简单，里面有两条生产上踩出来的约束，原样保留：

  · **原子替换**：Compose 的 file-backed secret 是按 inode 绑定的。
    就地改写会让已挂载的容器读到半截内容；先写临时文件再 `os.replace`。
  · **保留属主**：生产机上这些 secret 属于非 root 的 10001:10001（0640），
    是 Docker 与 systemd 共用的那座桥。以 root 身份刷新时如果不显式 chown 回去，
    会重建成 root-only，Core 就再也读不到自己的令牌了。
"""
from __future__ import annotations

import argparse
import os
import secrets
from pathlib import Path


def atomic_secret(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.stat() if path.exists() else None
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(value + "\n", encoding="utf-8")
    os.chmod(temp, (existing.st_mode & 0o777) if existing else 0o600)
    if existing is not None and os.geteuid() == 0:
        os.chown(temp, existing.st_uid, existing.st_gid)
    os.replace(temp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="确保 Social Archive 长期 API 令牌存在")
    parser.add_argument("--token-file", type=Path, default=Path("/run/secrets/social_archive_api_token"))
    args = parser.parse_args()
    # 幂等：已有非空令牌就原样不动。重新生成会把所有已连接的设备踢下线。
    if args.token_file.exists() and args.token_file.read_text(encoding="utf-8").strip():
        return 0
    atomic_secret(args.token_file, secrets.token_urlsafe(48))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
