"""文档让人跑的东西必须真的存在（v0.0.0.7 / T18）。

运维手册第 14 行写着 `bash scripts/restore.sh --dry-run <恢复点>`。
**那一句是出事那天才会被人读到的**，那时再发现脚本不在是最坏的时机，
而且那时候没人有心情去翻仓库。
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts/check_docs_point_at_things_that_exist.py"

# git 钩子会把这些塞进环境；子进程继承之后会去问**主仓**而不是沙盒。
_LEAKED_BY_GIT_HOOKS = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE",
                        "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")
_CLEAN_GIT_ENV = {k: v for k, v in os.environ.items() if k not in _LEAKED_BY_GIT_HOOKS}


def _run(root: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess:
    """**故意不洗环境。**

    pre-commit 跑这道门时，环境里就是带着 GIT_DIR 的。判据要是先替它洗一遍，
    检查器自己漏没漏那一步就再也测不出来了——那正是它出问题的场景。
    """
    argv = [sys.executable, str(CHECK)]
    if root is not None:
        argv += ["--root", str(root)]
    return subprocess.run(argv, cwd=ROOT, env=env,
                          capture_output=True, text=True, check=False)


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


def _git_sandbox(tmp_path: Path, doc_text: str, ignore: str) -> Path:
    """一个**真 git 仓**的沙盒——`git check-ignore` 得有仓才答得出话。

    **`git init` 也要摘掉钩子塞进来的环境变量。** pre-commit 跑测试时
    环境里有 GIT_DIR，`git init` 会去初始化**那个**目录而不是 tmp_path，
    沙盒于是根本没有 .git，判据便红在一个和它无关的地方。

    第一版还把 init 的退出码 `check=False` 吞了——**失败了也一声不吭**，
    正是今天在别处修过的那种写法。
    """
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    (tmp_path / "docs/手册.md").write_text(doc_text, encoding="utf-8")
    done = subprocess.run(["git", "init", "-q"], cwd=tmp_path, env=_CLEAN_GIT_ENV,
                          capture_output=True, text=True, check=False)
    assert done.returncode == 0, f"沙盒建不出 git 仓：{done.stdout}{done.stderr}"
    assert (tmp_path / ".git").is_dir(), "git init 报成功，而 .git 不在沙盒里"
    return tmp_path


def test_it_catches_a_code_block_using_a_gitignored_artifact(tmp_path) -> None:
    """**这类漏我肉眼看不出来：我这台机器上那个文件就在那儿。**

    交接里真写过这一段——`dist/` 在 .gitignore 第 41 行，
    照着敲的人第一步就卡住，而我怎么读都读不出问题。
    """
    root = _git_sandbox(
        tmp_path,
        "```\nunzip -q -o dist/social-archive-extension.zip -d /tmp/x\n```\n",
        "dist/\n")
    done = _run(root)
    assert done.returncode != 0, "代码块让人用一个 gitignore 挡着的文件，这道门却放过了"
    assert "只有作者机器上有" in done.stdout, done.stdout


def test_a_code_block_that_builds_it_first_is_fine(tmp_path) -> None:
    """同一个代码块里先有一条造它的命令，就不是漏。"""
    root = _git_sandbox(
        tmp_path,
        "```\npython3 scripts/build_extension_package.py\n"
        "unzip -q -o dist/social-archive-extension.zip -d /tmp/x\n```\n",
        "dist/\n")
    # 那条造包的命令自己也得存在，否则红的是**另一条规则**（让人跑不存在的脚本）。
    # 第一版忘了造它，于是这条判据红在了它不打算验的地方。
    (root / "scripts/build_extension_package.py").write_text("", encoding="utf-8")
    done = _run(root)
    assert done.returncode == 0, done.stdout


def test_a_tracked_path_in_a_code_block_is_not_flagged(tmp_path) -> None:
    """没被 gitignore 挡的路径不归这条规则管。

    实测过「查代码块里所有路径」那种写法：5 处命中**全是误报**
    （`L0/L1`、`origin/main` 这类带斜杠的散文和 git 引用）。
    """
    root = _git_sandbox(tmp_path, "```\ncat docs/手册.md\n```\n", "dist/\n")
    done = _run(root)
    assert done.returncode == 0, done.stdout


def test_the_check_does_not_ask_whether_the_file_happens_to_exist(tmp_path) -> None:
    """**「在不在」恰恰是那个骗人的信号。**

    文件在作者机器上存在，正是这类漏藏得住的原因。所以判据只问 .gitignore。
    这里把那个文件真造出来——它必须照样红。
    """
    root = _git_sandbox(
        tmp_path, "```\nunzip -q -o dist/pkg.zip -d /tmp/x\n```\n", "dist/\n")
    (root / "dist").mkdir(exist_ok=True)
    (root / "dist/pkg.zip").write_text("我在作者机器上是存在的\n", encoding="utf-8")
    done = _run(root)
    assert done.returncode != 0, "文件恰好存在，这道门就放过了——那正是漏的成因"


def test_it_survives_the_environment_a_git_hook_hands_it(tmp_path) -> None:
    """**这道门最常跑的地方就是 pre-commit，而钩子会塞 GIT_DIR 进环境。**

    子进程继承之后，`git check-ignore` 会拿着它去问**主仓**而不是 cwd 那个仓。
    第一次撞上时它表现为「单独跑绿、提交时红」的偶发失败——而根本不偶发，
    只在钩子里必错。
    """
    root = _git_sandbox(
        tmp_path, "```\nunzip -q -o dist/pkg.zip -d /tmp/x\n```\n", "dist/\n")
    dirty = dict(os.environ)
    dirty["GIT_DIR"] = str(ROOT / ".git")
    dirty["GIT_INDEX_FILE"] = str(ROOT / ".git/index")
    done = _run(root, env=dirty)
    assert done.returncode != 0, (
        "带着钩子的环境变量跑，这道门就答错了——它去问了主仓，不是 cwd 那个仓\n"
        + done.stdout + done.stderr
    )
    assert "只有作者机器上有" in done.stdout, done.stdout


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
