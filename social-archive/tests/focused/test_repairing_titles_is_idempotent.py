r"""修标题这一步必须可以反复跑——不然它会把他的库弄乱（2026-08-10）。

## 这条判据是从一次真事故来的

我在 Owner 的 Obsidian 库里手工修好 47 个标题（连文件名一起换），
**接着又跑了一次同步脚本**。那个脚本把服务器上那份**没修过**的文件
rsync 进来——同一条内容于是有了两个文件（干净的 + 脏的），
他库里的 md 从 194 变成 241。**是我把他的库弄乱的。**

（服务器上那批是「标题修复」上线之前生成的；部署卡在主机磁盘 5G 闸门上，
重新生成不了。）

修法不是「记得别重跑」，是**让同步脚本在合并进库之前先修**
（`repair_markdown_titles.py`）。这条判据钉的就是那一步：
它得真的修、修完再跑不变、并且不碰本来就正常的文件。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/repair_markdown_titles.py"


def _write(root: Path, name: str, title: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nplatform: \"douyin\"\n---\n\n# {title}\n\n正文\n", encoding="utf-8")
    return path


def _run(root: Path) -> str:
    done = subprocess.run([sys.executable, str(SCRIPT), str(root), "--apply"],
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr
    return done.stdout


def test_it_repairs_the_title_and_the_filename(tmp_path) -> None:
    _write(tmp_path / "douyin",
           "1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡-ac1720b2.md",
           "1029找卖萌办校园卡不后悔#校园卡找卖萌办校园卡不后悔#校园卡")
    _run(tmp_path)
    files = list((tmp_path / "douyin").glob("*.md"))
    assert len(files) == 1, files
    assert files[0].name == "找卖萌办校园卡不后悔校园卡-ac1720b2.md", files[0].name
    assert "# 找卖萌办校园卡不后悔#校园卡\n" in files[0].read_text(encoding="utf-8")


def test_running_it_twice_changes_nothing(tmp_path) -> None:
    """**幂等**——这正是那次事故的要害：跑第二次不能再生出一个文件。"""
    _write(tmp_path / "douyin", "2.0万真正的一次性她来了真正的一次性她来了-abcd1234.md",
           "2.0万真正的一次性她来了真正的一次性她来了")
    _run(tmp_path)
    after_first = sorted(p.name for p in (tmp_path / "douyin").glob("*.md"))
    second = _run(tmp_path)
    after_second = sorted(p.name for p in (tmp_path / "douyin").glob("*.md"))
    assert after_first == after_second, (after_first, after_second)
    assert len(after_second) == 1, after_second
    assert "已修 0 个标题" in second, second


def test_a_normal_note_is_untouched(tmp_path) -> None:
    path = _write(tmp_path / "bilibili", "一条正常的笔记-11112222.md", "一条正常的笔记")
    before = path.read_text(encoding="utf-8")
    _run(tmp_path)
    assert path.exists(), "本来就正常的文件被改名了"
    assert path.read_text(encoding="utf-8") == before


def test_the_pull_script_repairs_before_merging(tmp_path) -> None:
    """**接上了才算数。** 这个仓栽过六次以上「建好了没接上」。"""
    shell = (ROOT / "scripts/pull_markdown_to_obsidian.sh").read_text(encoding="utf-8")
    assert "repair_markdown_titles.py" in shell, (
        "同步脚本没有在合并进库之前修标题——"
        "服务器上那批是修复之前生成的，拉下来还是脏的，"
        "而他库里已经有修好的那份：两边一撞就是重复文件")
    # **真正算数的是合并之后那一次。**（2026-08-10）
    # 上一版断言「修必须排在合并之前」——那个模型是错的：只修下载的那份，
    # 库里还留着上一轮的旧文件名，rsync 只加不删，两份并存。
    # 修库才自愈。所以这里要的是：合并之后**还有**一次修。
    merge_at = shell.index("rsync -a")
    assert "repair_markdown_titles.py" in shell[merge_at:], (
        "合并进库之后没有再修一次——库里上一轮留下的旧文件名不会被清掉，"
        "同一条内容会留两份（他库里因此从 193 涨到 241、又从 198 涨到 246）")


def test_the_old_dirty_copy_is_dropped_when_the_clean_one_exists(tmp_path) -> None:
    """**同一条内容不许留两份。**（2026-08-10 我为此弄乱他的库两次）

    第一次：手工修好标题后又跑了一次同步，服务器上的旧文件名被 rsync 带回来
    ——他库里 193 变 241。
    第二次：我"修好"之后只在下载的那份上处理，库里旧名字还在，198 变 246，
    **而且稳定在错的状态**——那比一次性弄乱更坏，因为看起来「跑完了」。

    根因是我一直在处理**搬运过程**，而正确的做法是处理**库本身**：
    改完标题发现正确命名的那份已经在了，这一份就是重复的，删掉。
    """
    folder = tmp_path / "douyin"
    _write(folder, "找卖萌办校园卡不后悔校园卡-ac1720b2.md", "找卖萌办校园卡不后悔#校园卡")
    _write(folder, "1029找卖萌办校园卡不后悔校园卡找卖萌办校园卡不后悔校园卡-ac1720b2.md",
           "1029找卖萌办校园卡不后悔#校园卡找卖萌办校园卡不后悔#校园卡")
    assert len(list(folder.glob("*.md"))) == 2
    _run(tmp_path)
    left = list(folder.glob("*.md"))
    assert len(left) == 1, [p.name for p in left]
    assert left[0].name == "找卖萌办校园卡不后悔校园卡-ac1720b2.md", left[0].name


def test_it_converges_and_stays_there(tmp_path) -> None:
    """**跑几次都一样。** 他那次「稳定在错的状态」就是收敛到了错的地方，
    所以光验「跑两次不变」不够——还要验它收敛到**对**的那个数。"""
    folder = tmp_path / "douyin"
    _write(folder, "真正的一次性她来了-aaaa1111.md", "真正的一次性她来了")
    _write(folder, "2.0万真正的一次性她来了真正的一次性她来了-aaaa1111.md",
           "2.0万真正的一次性她来了真正的一次性她来了")
    _write(folder, "一条正常的-bbbb2222.md", "一条正常的")
    counts = []
    for _ in range(3):
        _run(tmp_path)
        counts.append(len(list(folder.glob("*.md"))))
    assert counts == [2, 2, 2], counts
