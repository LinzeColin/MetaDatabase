r"""不用 ssh 也能把内容装进他的 Obsidian 库（2026-08-10）。

## 为什么这条是必须的，不是锦上添花

新生产机（OVH VPS-3，2026-08-10 起）**对公网只开 80/443/8080/8000/6001-6002**
——ssh 不对外。也就是说桌面那个「ssh + tar 拉 Markdown」的做法在新机器上
**不是暂时连不上，是根本走不通**。

而他要的就是「东西进 Obsidian」。所以取法必须改成他真的做得到的那条：
资料库页面右上角「下载全部 Markdown」→ zip 落进下载文件夹 → 双击那个 .command。
浏览器里他本来就是登录状态，不需要粘任何令牌。

## 这条判据跑的是他双击的那个文件

不是「脚本里那段逻辑」，是 `scripts/同步到 Obsidian.command` 本身，
喂一个和生产同形的 zip（带互动数标题、作者字段装着点赞数），
看它是不是真的把库变成对的样子。
"""

from __future__ import annotations

import re
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
LAUNCHER = ROOT / "scripts/同步到 Obsidian.command"


def _note(platform: str, title: str, author: str, url: str) -> str:
    return (f'---\nplatform: "{platform}"\nurl: "{url}"\nauthor: "{author}"\n'
            f'relation_types: ["favorite"]\n---\n\n# {title}\n\n原始链接：{url}\n')


@pytest.fixture()
def bundle(tmp_path: Path) -> Path:
    """和生产下发的那个 zip 同形：按平台分目录，文件名带 8 位哈希尾巴。"""
    path = tmp_path / "markdown.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("douyin/x-aaaa1111.md", _note(
            "douyin", "2.0万测试标题测试标题", "26.6万",
            "https://www.douyin.com/video/7669728491277851091"))
        archive.writestr("bilibili/y-bbbb2222.md", _note(
            "bilibili", "一条正常的", "雪瑜", "https://www.bilibili.com/video/BV1"))
    return path


def _run(vault: Path, zip_path: Path) -> str:
    done = subprocess.run(
        ["bash", str(LAUNCHER), str(vault)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        env={"HOME": str(vault.parent), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
             "SOCIAL_ARCHIVE_MARKDOWN_ZIP": str(zip_path)})
    assert "用下载好的压缩包" in done.stdout, (
        "它没走「下载好的 zip」那条路——新生产机不开 ssh，走不通那条就等于没有取法\n"
        + done.stdout[-800:] + done.stderr[-400:])
    return done.stdout


def test_it_loads_the_vault_from_a_downloaded_zip(tmp_path: Path, bundle: Path) -> None:
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    _run(vault, bundle)
    files = sorted(p.relative_to(vault).as_posix() for p in vault.rglob("*.md"))
    assert files == ["Social Archive/bilibili/y-bbbb2222.md",
                     "Social Archive/douyin/测试标题-aaaa1111.md"], files


def test_the_interaction_count_titles_and_authors_are_cleaned(tmp_path: Path, bundle: Path) -> None:
    """他打开笔记看到的东西：标题不是「2.0万文案文案」，作者不是点赞数。"""
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    _run(vault, bundle)
    douyin = (vault / "Social Archive/douyin/测试标题-aaaa1111.md").read_text(encoding="utf-8")
    assert "author: null" in douyin, douyin
    assert re.search(r"^# 测试标题$", douyin, re.M), douyin
    bilibili = (vault / "Social Archive/bilibili/y-bbbb2222.md").read_text(encoding="utf-8")
    assert 'author: "雪瑜"' in bilibili, "真名被误清了"


def test_running_it_twice_leaves_the_same_vault(tmp_path: Path, bundle: Path) -> None:
    """**可以反复双击。** 他库里被「只修下载那份」的写法弄乱过两次。"""
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    _run(vault, bundle)
    first = sorted((p.name, p.read_text(encoding="utf-8")) for p in vault.rglob("*.md"))
    _run(vault, bundle)
    second = sorted((p.name, p.read_text(encoding="utf-8")) for p in vault.rglob("*.md"))
    assert first == second, "跑第二次库就变了"


def test_it_tells_him_what_to_do_when_there_is_no_zip_and_no_ssh(tmp_path: Path) -> None:
    """**失败要给出他做得到的下一步**，不能只说「连不上」。"""
    vault = tmp_path / "Obsidian"
    vault.mkdir()
    (tmp_path / "Downloads").mkdir()
    done = subprocess.run(
        ["bash", str(LAUNCHER), str(vault)],
        capture_output=True, text=True, check=False, stdin=subprocess.DEVNULL,
        env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
             "SOCIAL_ARCHIVE_HOST": "no-such-host-for-this-test"})
    assert "下载全部 Markdown" in done.stdout, (
        "连不上时没告诉他还能怎么办——他会卡在这里\n" + done.stdout[-600:])
