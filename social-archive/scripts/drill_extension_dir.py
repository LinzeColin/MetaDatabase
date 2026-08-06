#!/usr/bin/env python3
"""演练要用的那个扩展目录：**没给就用发布包**。

## 为什么

七个扩展演练都要 `--ext-dir`，而那个目录不会凭空存在——你得先
`python scripts/build_extension_package.py` 再 `unzip` 到某处。
**要先做两步准备才跑得动的演练，就是没人跑的演练。**

这个仓刚为此付过账：15 个演练调用方 0；其中一个连自己起 Chrome 都不会，
只抛一句 `Connection refused`，看起来像它坏了。

默认改成发布包解出来的那一份还有第二个好处：
**它们从此默认验的是他真正下载的那个 zip**，而不是某人随手指的一个目录。

## 用法

    from drill_extension_dir import resolve_ext_dir
    parser.add_argument("--ext-dir", default=None, help="不给就用 dist 里的发布包")
    ...
    ext_dir = resolve_ext_dir(args.ext_dir)
"""

from __future__ import annotations

import atexit
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "dist" / "social-archive-extension.zip"


def resolve_ext_dir(given: str | None) -> str:
    """给了就原样用，没给就现打包再解出来（临时目录在进程退出时自动收）。"""
    if given:
        path = Path(given).expanduser().resolve()
        if not path.is_dir():
            raise SystemExit(f"--ext-dir 指的不是一个目录：{path}")
        return str(path)

    # **现打一次包**：默认要验的是"他真正下载的那一份"，
    # 而 dist 里那个可能比源码旧（那正是 shipped_package_drill 抓过的一种）。
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_extension_package.py")],
                   check=True, stdout=subprocess.DEVNULL)
    if not PACKAGE.is_file():
        raise SystemExit(f"发布包不存在：{PACKAGE}")
    workspace = Path(tempfile.mkdtemp(prefix="sa-extdir-"))
    with zipfile.ZipFile(PACKAGE) as archive:
        archive.extractall(workspace)
    # **收尾挂在 atexit 上，不动调用方的控制流。**
    #
    # 让每个演练自己 try/finally 意味着要改它们的 main()——我试过一次，
    # 用正则盲改把八个文件同时弄坏了。这里改成进程退出时收，
    # 调用方只多一行「取目录」，控制流一个字不动。
    atexit.register(lambda: shutil.rmtree(workspace, ignore_errors=True))
    return str(workspace)
