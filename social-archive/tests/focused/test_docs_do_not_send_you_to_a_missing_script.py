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


def _run(cwd: Path = ROOT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(CHECK)], cwd=cwd,
                          capture_output=True, text=True, check=False)


def test_it_passes_right_now() -> None:
    done = _run()
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_catches_a_doc_that_points_at_nothing(tmp_path, monkeypatch) -> None:
    """**先验它能红。** 一个永远绿的门比没有门更坏——它让人以为查过了。

    第一次写这条反例时用了个中文文件名，而检查器的正则只认 ASCII，
    于是反例根本没触发，检查器「通过」了。差一点就据此说它管用。
    """
    manual = ROOT / "docs/06_运维手册.md"
    original = manual.read_text(encoding="utf-8")
    try:
        manual.write_text(original + "\n执行 `bash scripts/no_such_script_here.sh`。\n",
                          encoding="utf-8")
        done = _run()
        assert done.returncode != 0, "文档指向一个不存在的脚本，这道门却放过了"
        assert "no_such_script_here.sh" in done.stdout
    finally:
        manual.write_text(original, encoding="utf-8")


def test_the_whitelist_is_load_bearing_not_decorative() -> None:
    """白名单里那份文档是**故意**点名已删除脚本的（开头写着「不要照着旧内容操作」）。

    把它从白名单里拿掉必须立刻报错——否则说明白名单根本没在起作用，
    而一个不起作用的白名单会掩盖真问题。
    """
    source = CHECK.read_text(encoding="utf-8")
    assert "DOMESTIC_WORKERS_ZH.md" in source
    patched = source.replace('"DOMESTIC_WORKERS_ZH.md":', '"_disabled_":', 1)
    assert patched != source
    try:
        CHECK.write_text(patched, encoding="utf-8")
        done = _run()
        assert done.returncode != 0, "白名单是装饰性的——拿掉它什么都没发生"
        assert "start_workers.sh" in done.stdout
    finally:
        CHECK.write_text(source, encoding="utf-8")


def test_the_whitelisted_doc_actually_warns_the_reader() -> None:
    """白名单只对**明确标了作废**的文档开口。

    没有那句警告的话，白名单就成了「把问题藏起来」的开关。
    """
    doc = (ROOT / "docs/DOMESTIC_WORKERS_ZH.md").read_text(encoding="utf-8")
    head = "\n".join(doc.splitlines()[:8])
    assert "不要照着" in head, "这份文档在白名单里，却没在开头告诉读者别照着做"
