"""文档让人跑的东西必须真的存在（v0.0.0.7 / T18）。

运维手册第 14 行写着 `bash scripts/restore.sh --dry-run <恢复点>`。
**那一句是出事那天才会被人读到的**，那时再发现脚本不在是最坏的时机，
而且那时候没人有心情去翻仓库。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_docs_point_at_things_that_exist.py"


def _run(root: Path | None = None) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(CHECK)]
    if root is not None:
        argv += ["--root", str(root)]
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, check=False)


def _sandbox(tmp_path: Path, doc_text: str) -> Path:
    """造一份只有 docs/ 与 scripts/ 的临时小仓，**绝不碰真文档**。

    原来这条反例是直接改 docs/06_运维手册.md 再改回来。那样的判据
    **不可重入**：跑到一半被打断就把改坏的文档留在工作树里，
    两次同时跑还会互相踩——本会话就出现过一次无法归因的偶发失败。
    """
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/手册.md").write_text(doc_text, encoding="utf-8")
    return tmp_path


def test_it_passes_right_now() -> None:
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_catches_a_doc_that_points_at_nothing(tmp_path) -> None:
    """**先验它能红。** 一个永远绿的门比没有门更坏——它让人以为查过了。

    第一次写这条反例时用了个中文文件名，而检查器的正则只认 ASCII，
    于是反例根本没触发，检查器「通过」了。差一点就据此说它管用。
    """
    root = _sandbox(tmp_path, "执行 `bash scripts/no_such_script_here.sh`。\n")
    done = _run(root)
    assert done.returncode != 0, "文档指向一个不存在的脚本，这道门却放过了"
    assert "no_such_script_here.sh" in done.stdout


def test_it_accepts_a_doc_that_points_at_something_real(tmp_path) -> None:
    """反例的对照面：脚本真的在，就必须放行——否则它只是个永远喊红的门。"""
    root = _sandbox(tmp_path, "执行 `bash scripts/restore.sh`。\n")
    (root / "scripts/restore.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    done = _run(root)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_whitelist_is_load_bearing_not_decorative() -> None:
    """白名单里那份文档是**故意**点名已删除脚本的（开头写着「不要照着旧内容操作」）。

    把它从白名单里拿掉必须立刻报错——否则说明白名单根本没在起作用。
    这里不改仓里的检查器：把源码读出来、改一份放进临时目录再跑。
    """
    import tempfile

    source = CHECK.read_text(encoding="utf-8")
    assert "DOMESTIC_WORKERS_ZH.md" in source
    patched = source.replace('"DOMESTIC_WORKERS_ZH.md":', '"_disabled_":', 1)
    assert patched != source
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "check_copy.py"
        copy.write_text(patched, encoding="utf-8")
        done = subprocess.run([sys.executable, str(copy), "--root", str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode != 0, "白名单是装饰性的——拿掉它什么都没发生"
    assert "start_workers.sh" in done.stdout


def test_the_whitelisted_doc_actually_warns_the_reader() -> None:
    """白名单只对**明确标了作废**的文档开口。

    没有那句警告的话，白名单就成了「把问题藏起来」的开关。
    """
    doc = (ROOT / "docs/DOMESTIC_WORKERS_ZH.md").read_text(encoding="utf-8")
    head = "\n".join(doc.splitlines()[:8])
    assert "不要照着" in head, "这份文档在白名单里，却没在开头告诉读者别照着做"
