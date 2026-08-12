r"""超长标题不许把整轮修复打死（2026-08-10）。

## 从哪来

在**生产的导出目录**上真跑修复脚本，第一个文件就崩：

    OSError: [Errno 36] File name too long:
      '…/咕咕嘎嘎😜咕咕嘎嘎🤪…-af61d356.md'

原来写的是 `[:80]` —— 80 个**字符**。而 ext4/APFS 限的是 **255 字节**，
中文 3 字节、emoji 4 字节，80 个字符能到 320 字节。
**他的 Obsidian 库里就有一个 268 字节的文件名**，所以这不是理论问题。

而且崩的是第一个文件，**其余 192 条一条都没被修到** —— 一个坏文件打死了整轮。

## 钉两件

1. 生成的文件名按**字节**截，且不把多字节字符切成两半；
2. 单个文件出错只跳过它，整轮继续。
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/repair_markdown_titles.py"


def _module():
    spec = importlib.util.spec_from_file_location("repair", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_the_generated_name_fits_the_filesystem() -> None:
    fit = _module()._fit_filename
    for title in ["咕咕嘎嘎😜" * 40, "人类需要很多很多晴天和阳光" * 20, "a" * 500, "短"]:
        out = fit(title, "-af61d356.md")
        whole = f"{out}-af61d356.md".encode("utf-8")
        assert len(whole) <= 255, f"{len(whole)} 字节，超过文件系统上限：{out[:20]}…"
        assert out.encode("utf-8").decode("utf-8") == out, "把多字节字符切成两半了"


def test_a_real_long_name_survives_a_full_run(tmp_path: Path) -> None:
    """整轮跑完，不许崩在某一个文件上。"""
    folder = tmp_path / "douyin"
    folder.mkdir(parents=True)
    long_title = "咕咕嘎嘎😜咕咕嘎嘎🤪" * 12          # 双份，会触发「左右两半相同」
    (folder / "long-af61d356.md").write_text(
        f'---\nplatform: "douyin"\n---\n\n# {long_title}\n', encoding="utf-8")
    # **夹具要够长**：`clean_display_title` 要求去掉数字前缀后左右各 ≥3 个字，
    # 第一版写的是「甲甲甲甲」（每半 2 个字），于是它压根没被判成重复标题，
    # 测出来「修了 0 个」——**夹具够不着要测的那条路**。
    (folder / "2.0万甲乙丙甲乙丙-bbbb2222.md").write_text(
        '---\nplatform: "douyin"\n---\n\n# 2.0万甲乙丙甲乙丙\n', encoding="utf-8")
    done = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--apply"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Errno 36" not in done.stderr, done.stderr
    names = sorted(p.name for p in folder.glob("*.md"))
    assert len(names) == 2, names
    for name in names:
        assert len(name.encode("utf-8")) <= 255, f"{name} 有 {len(name.encode())} 字节"


def test_one_bad_file_does_not_kill_the_run(tmp_path: Path) -> None:
    """**一个文件坏了不许打死整轮。** 生产上就是这样：其余 192 条一条没修到。"""
    folder = tmp_path / "douyin"
    folder.mkdir(parents=True)
    (folder / "2.0万甲乙丙甲乙丙-aaaa1111.md").write_text(
        '---\nplatform: "douyin"\n---\n\n# 2.0万甲乙丙甲乙丙\n', encoding="utf-8")
    broken = folder / "broken-cccc3333.md"
    broken.symlink_to(tmp_path / "does-not-exist.md")     # 读它必然出错
    done = subprocess.run([sys.executable, str(SCRIPT), str(tmp_path), "--apply"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert (folder / "甲乙丙-aaaa1111.md").exists(), (
        "坏文件把整轮打死了，好文件没被修到：\n" + done.stdout + done.stderr)
