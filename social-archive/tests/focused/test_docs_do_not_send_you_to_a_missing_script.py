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


def test_the_deletion_record_rule_is_load_bearing_not_decorative() -> None:
    """放行「已删 `scripts/xxx`」的那条规则，拿掉必须立刻报错。

    这条判据换过一次靶子。原来它盯的是一张**按整份文档**开的白名单
    （只为 `docs/DOMESTIC_WORKERS_ZH.md` 一份而设）。改成按行判之后，
    那张白名单变成了纯装饰——而**正是这条判据把它点红的**：拿掉白名单，
    检查器照样绿。于是白名单删掉，判据改盯真正承重的那条规则。
    """
    import tempfile

    source = CHECK.read_text(encoding="utf-8")
    patched = source.replace("RECORDS_A_DELETION = (", "RECORDS_A_DELETION = ()  # noqa\n_UNUSED = (", 1)
    assert patched != source, "检查器里已经没有 RECORDS_A_DELETION 了"
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "check_copy.py"
        copy.write_text(patched, encoding="utf-8")
        done = subprocess.run([sys.executable, str(copy), "--root", str(ROOT)],
                              cwd=ROOT, capture_output=True, text=True, check=False)
    assert done.returncode != 0, "放行规则是装饰性的——拿掉它什么都没发生"
    assert "start_workers.sh" in done.stdout, done.stdout


def test_a_deletion_record_is_not_read_as_an_instruction(tmp_path) -> None:
    """「已删 `scripts/xxx`」是记录，不是让人去跑——包括**折行**的那种。

    交接里真有这么一句：「已删」在上一行，`stop_workers.sh` 折到了下一行。
    只看本行就会把它报成「让人跑一个不存在的脚本」。
    """
    root = _sandbox(tmp_path, "已删 `scripts/gone_a.sh`\n+ `scripts/gone_b.sh`。\n")
    done = _run(root)
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_deletion_record_does_not_taint_the_next_line(tmp_path) -> None:
    """**放宽用宽窗，指控用窄窗。**

    「说已删而它还在」这一侧要是也看两行，下面第二行的 real.sh 就会被
    上一行的「已删」牵连，报成「说它已删而它还在」——又是一次指错原因。
    """
    root = _sandbox(tmp_path, "已删 `scripts/gone.sh`。\n现在改用 `scripts/real.sh`。\n")
    (root / "scripts/real.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    done = _run(root)
    assert done.returncode == 0, done.stdout + done.stderr


def test_it_catches_a_deletion_record_that_is_not_true(tmp_path) -> None:
    """反过来也要抓：写着「已删」而它还在。删漏了，或者这句记录是错的。"""
    root = _sandbox(tmp_path, "已删 `scripts/still_here.sh`。\n")
    (root / "scripts/still_here.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    done = _run(root)
    assert done.returncode != 0, "文档说它已删，而它还在，这道门却放过了"
    assert "记录与事实不符" in done.stdout, done.stdout


def test_the_handoff_is_scanned_too(tmp_path) -> None:
    """**接手的人第一份读的是交接，而它原来整个在这道门的视野之外。**

    这道门原来只扫 docs/。往交接里写「要加新平台就跑这个」的那天才发现。
    """
    (tmp_path / "evidence").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "evidence/HANDOFF.md").write_text(
        "跑一下 `scripts/nothing_here.sh`。\n", encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode != 0, "交接里指向一个不存在的脚本，这道门却放过了"
    assert "nothing_here.sh" in done.stdout


def test_a_markdown_at_the_repo_root_is_scanned(tmp_path) -> None:
    """**范围漏过两次，两次都是同一天。**

    先只扫 docs/（漏了 evidence/ 里的交接），补上之后才发现仓根还有一份
    `HANDOFF.md`，19 处引用，同样在门外。列目录的白名单每补一次就等下一次漏，
    所以现在全扫。
    """
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "随便一份.md").write_text("跑 `scripts/absent.sh`。\n", encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode != 0, "仓根的 md 没被扫到"
    assert "absent.sh" in done.stdout


def test_a_path_into_a_sibling_repo_is_not_flagged(tmp_path) -> None:
    """`../隔壁仓/…/scripts/x.py` 不是本仓的引用，本仓没有它是正常的。

    原来的正则见 `scripts/` 就算数，把 HANDOFF.md 里那条隔壁仓路径截出尾巴
    报成缺陷。**指错原因比不报更糟**——会让人去补一个本来就不该在这儿的文件。
    """
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "手册.md").write_text(
        "python ../social-archive-taskpack-compat/v0.0.0.4/scripts/validate_compatibility.py\n",
        encoding="utf-8")
    done = _run(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr

    # 对照面：去掉前面那段外部路径，它就该被抓。
    (tmp_path / "手册.md").write_text("python scripts/validate_compatibility.py\n",
                                      encoding="utf-8")
    assert _run(tmp_path).returncode != 0, "去掉外部前缀之后仍然放过——正则放得太松"


def test_the_stale_root_handoff_says_it_is_not_current() -> None:
    """仓根 `HANDOFF.md` 停在 v0.0.0.6，而当前那份在 evidence/ 里。

    名字最容易被点开的那一份，正文第三行写着「v0.0.0.6 current execution」。
    接手的人照着它判断今天的状态，会得到一个两个版本前的答案。
    """
    head = "\n".join((ROOT / "HANDOFF.md").read_text(encoding="utf-8").splitlines()[:14])
    assert "不是当前交接" in head, "仓根那份交接没说自己不是当前的"
    assert "evidence/HANDOFF_v0007.md" in head, "没有指出当前交接在哪"


def test_the_deprecated_doc_still_warns_the_reader() -> None:
    """那份作废文档必须在开头告诉读者别照着做。

    它现在靠「不要照着」这句话本身被放行——那句话既是给读者的警告，
    也是这道门放行它的依据。**警告没了，放行也就没了**，这是对的。
    """
    doc = (ROOT / "docs/DOMESTIC_WORKERS_ZH.md").read_text(encoding="utf-8")
    head = "\n".join(doc.splitlines()[:8])
    assert "不要照着" in head, "这份文档点名了已删脚本，却没在开头告诉读者别照着做"
