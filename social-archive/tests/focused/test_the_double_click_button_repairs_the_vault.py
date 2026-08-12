r"""把「同步到 Obsidian.command」里那段修库代码**抠出来真跑一遍**（2026-08-10）。

## 为什么不能只查字符串

Owner 双击的是那个 `.command` 文件，修库逻辑是内联在里面的一段 Python。
`repair_markdown_titles.py` 里那份是同样的意思，但**他跑不到那一份**。
这个仓的老毛病正是「判据验的是我摆好的夹具，不是他真会走的那条路」——
所以这里把 `.command` 里的第二段 heredoc 原样取出来执行，
夹具就是他库里真实出现过的那三种文件。

## 它守什么

1. 抖音那种「互动数 + 文案 + 文案」的标题要修好，文件名跟着换；
2. frontmatter 里 `author` 装着点赞数的要清成 null
   （生产实测：抖音 86 条里 31 条如此，他那条写着 `author: "26.6万"`）；
3. 正确命名的那份已经在了，脏的那份是重复，删掉；
4. **跑两次结果一样**——他库里因为这一条被我弄乱过两次（193→241、198→246）。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "scripts/同步到 Obsidian.command"


def _vault_repair_code() -> str:
    """取 `.command` 里第二段内联 Python——就是合并进库之后修库的那段。"""
    blocks = re.findall(r"<<'PYEOF'\n(.*?)\nPYEOF", WRAPPER.read_text(encoding="utf-8"), re.S)
    assert len(blocks) == 2, (
        f"`.command` 里内联 Python 段落数变成了 {len(blocks)}——"
        "这条判据按「第二段是修库」取的，结构变了就取错了")
    code = blocks[1]
    assert "vault" in code and "rglob" in code, "取到的不是修库那一段"
    return code


def _run(vault: Path) -> str:
    done = subprocess.run([sys.executable, "-", str(vault)],
                          input=_vault_repair_code(),
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def _note(folder: Path, name: str, *, title: str, author: str | None,
          url: str = "https://www.douyin.com/video/7669728491277851091") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    author_line = f'author: "{author}"' if author is not None else "author: null"
    path = folder / name
    path.write_text(
        f'---\nplatform: "douyin"\nurl: "{url}"\n{author_line}\n'
        f'relation_types: ["like"]\n---\n\n# {title}\n\n原始链接：{url}\n',
        encoding="utf-8")
    return path


def test_a_like_count_in_the_author_field_is_cleared(tmp_path: Path) -> None:
    """他那条笔记的 frontmatter 写着 `author: "26.6万"`——那是点赞数不是作者。"""
    note = _note(tmp_path / "douyin", "abc-11112222.md", title="随便", author="26.6万")
    _run(tmp_path)
    body = note.read_text(encoding="utf-8")
    assert "author: null" in body, body
    assert "26.6万" not in body.split("---")[1], "点赞数还留在 frontmatter 里"


@pytest.mark.parametrize("author", ["思维实验室", "小清新", "雪瑜", "收藏", "我的"])
def test_a_real_name_is_left_alone(tmp_path: Path, author: str) -> None:
    """**只清能自证的那一档。** `收藏`/`我的` 是页面上的字，但机器分不出它和
    「收藏家」这种真名——分不出就不动，宁可留错也不许改错。"""
    note = _note(tmp_path / "douyin", f"x-1111{len(author):04d}.md", title="随便", author=author)
    _run(tmp_path)
    assert f'author: "{author}"' in note.read_text(encoding="utf-8")


def test_the_doubled_title_is_repaired_and_the_file_renamed(tmp_path: Path) -> None:
    folder = tmp_path / "douyin"
    _note(folder, "1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡-ac1720b2.md",
          title="1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡", author=None)
    _run(tmp_path)
    left = list(folder.glob("*.md"))
    assert len(left) == 1, [p.name for p in left]
    assert left[0].name == "找卖萌办校园卡不后悔校园卡-ac1720b2.md", left[0].name


def test_the_dirty_copy_is_dropped_when_the_clean_one_is_already_there(tmp_path: Path) -> None:
    """rsync 每次都把服务器上的旧文件名带回来——不删就变两份。"""
    folder = tmp_path / "douyin"
    _note(folder, "找卖萌办校园卡不后悔校园卡-ac1720b2.md",
          title="找卖萌办校园卡不后悔校园卡", author=None)
    _note(folder, "1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡-ac1720b2.md",
          title="1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡", author=None)
    _run(tmp_path)
    left = [p.name for p in folder.glob("*.md")]
    assert left == ["找卖萌办校园卡不后悔校园卡-ac1720b2.md"], left


def test_it_converges_and_a_second_run_changes_nothing(tmp_path: Path) -> None:
    """**跑两次一样。** 他库里被我弄乱过两次，第二次还「稳定在错的状态」。"""
    folder = tmp_path / "douyin"
    _note(folder, "真正的一次性她来了-aaaa1111.md", title="真正的一次性她来了", author="26.6万")
    _note(folder, "2.0万真正的一次性她来了真正的一次性她来了-aaaa1111.md",
          title="2.0万真正的一次性她来了真正的一次性她来了", author="2.0万")
    _note(folder, "一条正常的-bbbb2222.md", title="一条正常的", author="雪瑜")
    states = []
    for _ in range(3):
        _run(tmp_path)
        states.append(sorted(
            (p.name, p.read_text(encoding="utf-8")) for p in folder.glob("*.md")))
    assert states[0] == states[1] == states[2], "跑第二次结果就变了"
    names = [name for name, _ in states[-1]]
    assert names == ["一条正常的-bbbb2222.md", "真正的一次性她来了-aaaa1111.md"], names
    kept = dict(states[-1])["真正的一次性她来了-aaaa1111.md"]
    assert "author: null" in kept, kept


def test_a_number_only_title_falls_back_to_the_link(tmp_path: Path) -> None:
    """标题整个就是个点赞数的，清完是空——得有兜底，不能留个空标题。"""
    note = _note(tmp_path / "douyin", "646-cccc3333.md", title="646", author=None)
    _run(tmp_path)
    left = list((tmp_path / "douyin").glob("*.md"))
    assert len(left) == 1, [p.name for p in left]
    body = left[0].read_text(encoding="utf-8")
    heading = re.search(r"^# (.+)$", body, re.M)
    assert heading and heading.group(1).strip(), f"标题被清空了：{body!r}"
    assert heading.group(1).strip() != "646", "点赞数还当着标题"
    assert "douyin.com" in heading.group(1), heading.group(1)
    assert note  # 名字可能已经换掉，这里只保证上面那一个文件在


def test_two_clean_copies_of_the_same_item_still_collapse_to_one(tmp_path: Path) -> None:
    """**两份标题都干净、只是文件名不同**——也只能留一个。（2026-08-10 第三次踩）

    前两次的规则是「保留标题已经干净的那份」。而我在**服务器**上也跑了一次修复、
    改了 48 个文件名之后，rsync 把新名字带进来，库里出现了两份都干净的：

        douyin/646-81ae07ff.md                              ← 旧名（服务器修完的）
        douyin/douyin.comvideo7669773688804784986-81ae07ff.md ← 库里那份的规范名

    那条规则分不出该删谁，于是他库里 193 变 198。
    改成看**文件名是不是它自己标题该有的样子**，留规范的那份。
    """
    folder = tmp_path / "douyin"
    url = "https://www.douyin.com/video/7669773688804784986"
    _note(folder, "646-81ae07ff.md", title="douyin.com/video/7669773688804784986",
          author=None, url=url)
    _note(folder, "douyin.comvideo7669773688804784986-81ae07ff.md",
          title="douyin.com/video/7669773688804784986", author=None, url=url)
    assert len(list(folder.glob("*.md"))) == 2
    _run(tmp_path)
    left = [p.name for p in folder.glob("*.md")]
    assert left == ["douyin.comvideo7669773688804784986-81ae07ff.md"], left


def test_an_empty_heading_is_never_left_behind(tmp_path: Path) -> None:
    """标题被清成空时要用链接兜底——**我在生产上写出过 4 个空的 `# `**。"""
    folder = tmp_path / "douyin"
    _note(folder, "646-81ae07ff.md", title="646", author=None)
    _run(tmp_path)
    left = list(folder.glob("*.md"))
    assert len(left) == 1, [p.name for p in left]
    body = left[0].read_text(encoding="utf-8")
    heading = re.search(r"^# (.*)$", body, re.M)
    assert heading and heading.group(1).strip(), f"留下了一个空标题：{body!r}"
