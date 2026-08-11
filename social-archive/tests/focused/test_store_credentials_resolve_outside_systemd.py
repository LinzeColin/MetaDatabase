"""取存储凭据的地方，都得能在 systemd 之外找到那两个文件（2026-08-10）。

## 它拦的是什么

`.env` 里写的凭据路径是 `/run/secrets/…`——**那是 systemd 的凭据目录
（unit 里的 `LoadCredential`），只在那个服务跑起来时才存在。**
在 unit 之外（手工跑一次恢复演练、在服务器上收拾东西）那两个文件读不到。

在他生产机上实测：

    R2_ACCESS_KEY_ID_FILE      配置指向存在吗= False | 回退后存在吗= True
    R2_SECRET_ACCESS_KEY_FILE  配置指向存在吗= False | 回退后存在吗= True
    OCI_ACCESS_KEY_ID_FILE     配置指向存在吗= False | 回退后存在吗= True

`restore_object.py` 早就有回退（`resolve_secret_path`，回到 `runtime/secrets/`
找同名文件），所以它一直能跑；而 `backup.py` 的 `_s3_config` 没有。

**后果不是"少个功能"**：`restore_runtime_db_drill.py` 从 `backup` 导入那个函数，
于是**唯一能证明「他的数据库拿得回来」的那个演练，结构上跑不起来**——
它在 `evidence/G3/ALL_DRILLS.json` 里一直挂在 `not_run`，
理由写的是「要真实的备份清单与远端存储」，而真实原因是这里。
2026-08-10 在他生产机上真去跑它才撞出来（报「r2 未配置」，而四个环境变量都设着）。

同源：「未测过的兜底分支只在别人机器上发作」——这条路我从没走过，
因为我平时是通过 systemd 跑它的。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = [ROOT / "scripts/backup.py", ROOT / "scripts/restore_object.py"]

pytestmark = pytest.mark.skipif(not TARGETS[0].is_file(), reason="backup.py 不存在")


def _bare_secret_reads(path: Path) -> list[int]:
    """`read_secret(os.getenv("…_FILE"))` —— 少了中间那层回退的写法。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    bad: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "read_secret"):
            continue
        if not node.args:
            continue
        inner = node.args[0]
        # 合格的写法：read_secret(resolve_secret_path(...))
        if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) \
                and inner.func.id == "resolve_secret_path":
            continue
        # 只管取「…_FILE」环境变量那一类
        source = ast.dump(inner)
        if "_FILE" in source or "getenv" in source:
            bad.append(node.lineno)
    return bad


def test_the_scanner_finds_read_secret_calls_at_all() -> None:
    """反空扫：一处 `read_secret(` 都没解析到的话，下面那条会白过。"""
    total = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        total += sum(1 for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                     and node.func.id == "read_secret")
    assert total >= 2, f"只解析到 {total} 处 read_secret——这条判据在空扫"


def test_store_credentials_always_go_through_the_fallback() -> None:
    hits = {str(path.relative_to(ROOT)): _bare_secret_reads(path)
            for path in TARGETS if path.is_file()}
    offenders = {path: lines for path, lines in hits.items() if lines}
    assert not offenders, (
        f"这些地方直接拿 `…_FILE` 读凭据、没走 resolve_secret_path：{offenders}——"
        "`.env` 里那两个路径是 systemd 的凭据目录，**在 unit 之外不存在**；"
        "少了回退，脚本会报「未配置」，而四个环境变量其实都设着。"
        "唯一能证明『他的数据库拿得回来』的那个演练就是这么被卡住的。")
