"""守住「生产上跑的是不是仓里这一份」（v0.0.0.7 / T18）。

`/opt/social-archive` **不是 git 检出**——代码是 rsync 送上去的，
那台机器上**没有 `git status` 可问**。2026-08-05 我自己往那儿 scp 过一个脚本，
事后想确认没弄脏，才发现要回答这件事得临时敲四条命令去拼。
而部署脚本第 8 道门只逐字节核了**扩展包**那一个文件，其余一百多个源文件
从来没有任何东西核过。

判据喂 `classify()` 两个字典，**不连任何机器**。
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECK_PATH = ROOT / "scripts/check_production_matches_the_repo.py"
CHECK_SOURCE = CHECK_PATH.read_text(encoding="utf-8")

_spec = importlib.util.spec_from_file_location("_production_drift", CHECK_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules["_production_drift"] = _module
_spec.loader.exec_module(_module)
classify = _module.classify


def _code_only(text: str) -> str:
    """只留代码：注释与**文档字符串**都去掉。

    第一版只去掉了以 `#` 开头的行，于是「这道门里不许出现 rsync」那条判据
    打在了模块开头那段说明文字上——**那段话正是在解释「代码是 rsync 送上去的」**。
    判据钉在散文上，今天已经栽过好几次；这次是反过来的方向：不是放过，是**冤枉**。
    """
    import ast

    tree = ast.parse(text)
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            docstring_lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return "\n".join(
        line for number, line in enumerate(text.splitlines(), 1)
        if number not in docstring_lines and not line.strip().startswith("#")
    )


def test_identical_sides_produce_nothing() -> None:
    """**先验它会绿。** 一个永远喊红的门等于没有门。"""
    same = {"scripts/a.py": "aaa", "src/b.py": "bbb"}
    assert classify(same, dict(same)) == {
        "only_on_production": [], "only_local": [], "differing": []}


def test_a_file_only_on_production_is_its_own_category() -> None:
    """**这一类最要紧：没人知道从哪来的代码，正在生产上跑。**

    手工改的、scp 上去的、旧版本删剩的，都会落在这里。
    """
    buckets = classify({"scripts/a.py": "aaa"},
                       {"scripts/a.py": "aaa", "scripts/mystery.py": "zzz"})
    assert buckets["only_on_production"] == ["scripts/mystery.py"]
    assert buckets["only_local"] == [] and buckets["differing"] == []


def test_a_file_only_local_is_not_confused_with_it() -> None:
    """「新写的还没发」和「生产上有来路不明的文件」要紧程度差得远。"""
    buckets = classify({"scripts/a.py": "aaa", "scripts/new.py": "nnn"},
                       {"scripts/a.py": "aaa"})
    assert buckets["only_local"] == ["scripts/new.py"]
    assert buckets["only_on_production"] == [], "把「还没部署」错报成了「来路不明」"


def test_the_three_categories_never_bleed_into_each_other() -> None:
    """三类同时出现时，各归各的——**混成一个数报出来等于什么都没说**。"""
    buckets = classify(
        {"a.py": "1", "only_here.py": "2", "changed.py": "local"},
        {"a.py": "1", "only_there.py": "3", "changed.py": "prod"})
    assert buckets["only_local"] == ["only_here.py"]
    assert buckets["only_on_production"] == ["only_there.py"]
    assert buckets["differing"] == ["changed.py"]


def test_only_on_production_and_logic_differences_are_what_fail_it() -> None:
    """只差注释不该把门点红，**但也不许被算成「相同」**——注释也是交接的一部分。

    实测：生产上的 backup.py 与仓里只差我今天写的一段注释，
    这道门把它归进 comment_only，而没有和真的逻辑漂移混在一起。
    """
    code = _code_only(CHECK_SOURCE)
    # 失败条件后来长了一项（镜像比仓旧），所以不钉死整句，钉三个组成部分。
    assert 'status = "FAIL" if' in code
    for part in ("only_on_production", "logic_differs", "container_stale"):
        assert part in code.split('status = "FAIL" if')[1].split("else")[0], (
            f"{part} 不在失败条件里"
        )
    assert '"comment_only": comment_only' in code, "只差注释的那一类没有单独报出来"


def test_an_empty_remote_listing_is_not_reported_as_agreement() -> None:
    """**远端一个文件都没数到，绝不能报成「一样」。**

    路径写错、sudo 没权限、ssh 连上了但 cd 失败——现象都是「零个文件」，
    而零个文件和全部一致在朴素的集合运算里长得一模一样。
    """
    assert "远端一个文件都没数到" in CHECK_SOURCE
    assert "NOTHING_TO_COMPARE" in CHECK_SOURCE, "本地空的时候也要拒绝，不能算通过"


def test_it_never_writes_to_production() -> None:
    """只读：ssh 过去只跑 find / sha256sum / cat，不写、不改、不重启。

    **查的是字符串字面量，不是整份源码。** 会跑到那台机器上的东西只可能
    是字面量；而对整份源码做子串匹配会冤枉人——第一版拿 `"> "` 找重定向，
    结果打在 `def _local_hashes() -> dict[str, str]:` 的返回标注上。
    判据自己指错原因，今天第三次。
    """
    import ast

    # **只取真正送进 subprocess.run(...) 的字符串。**
    #
    # 前两版都拿「所有字符串字面量」当命令，于是接连冤枉了两处：
    #   · 模块开头解释「代码是 rsync 送上去的」那段说明
    #   · 「systemctl restart 不会重建镜像」那句**给人看的提示**
    # 两处都不是要送去执行的东西。**判据自己指错原因，今天第四次。**
    # 会跑到那台机器上的只可能是 subprocess.run 的参数，那就只看它。
    tree = ast.parse(CHECK_SOURCE)
    commands: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        name = getattr(target, "attr", None) or getattr(target, "id", None)
        if name != "run":
            continue
        for argument in list(node.args) + [kw.value for kw in node.keywords]:
            for inner in ast.walk(argument):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    commands.append(inner.value)
                elif isinstance(inner, ast.JoinedStr):
                    commands.append("".join(
                        part.value for part in inner.values
                        if isinstance(part, ast.Constant) and isinstance(part.value, str)))
    assert commands, "一条送去执行的字符串都没找到——**这不是通过**，是这条判据瞎了"
    # `docker exec` 本身不危险——危险的是**用它做了什么**。这道门用它进容器
    # 数文件，那是只读的。所以禁的是会动容器的那些子命令，不是 docker 三个字母。
    for dangerous in ("rsync", "docker restart", "docker rm", "docker stop",
                      "docker compose", "docker cp", "systemctl", "rm -", "mv ",
                      " > ", "tee "):
        offenders = [text for text in commands if dangerous in text]
        assert not offenders, f"要送去生产执行的字符串里有 {dangerous!r}：{offenders[:1]}"

    # 进了容器之后跑的也必须只是读：只允许 find / sha256sum / xargs / cd。
    for text in commands:
        if "docker exec" not in text:
            continue
        for verb in ("python", "sh -c", "bash", "apt", "pip", "chown", "chmod"):
            assert verb not in text, f"docker exec 里出现了不是只读的动作：{verb!r}"

    # 而且真正会跑的那几个词必须在——否则这条判据可能只是「什么都没找到」。
    #
    # **这两条查整份源码，不查 subprocess 参数。** 和上面正好相反，是有意的：
    # 命令常常先拼进一个变量再传出去（`command = f"cd ... sha256sum ..."`），
    # AST 那条路看不见它。而这两条是**正向确认**，宽一点只会漏放行、不会冤枉人。
    # 指控用窄窗，确认用宽窗——今天在文档那道门上已经定过同一条规矩。
    assert "sha256sum" in CHECK_SOURCE, "没看到它真去算哈希"
    assert "find " in CHECK_SOURCE, "没看到它真去列文件"


def test_it_also_compares_the_copy_inside_the_image() -> None:
    """**要比的是三份，不是两份。**

    2026-08-05 才弄清楚：容器里的 `/app` 是**烤进镜像的**，不是主机目录的
    绑定挂载（只有 `/run/secrets/*` 是）。当天就撞上了——把修好的脚本放到
    主机上，在容器里跑，跑的还是旧的。

    只比「仓 ←→ 主机」会得出一个安心但不成立的结论：主机同步对了，
    **服务可能还在跑上一版**。运维手册那句「systemctl restart 不会重建镜像」
    说的是同一件事的另一面。
    """
    code = _code_only(CHECK_SOURCE)
    assert "_container_hashes" in code, "根本没去看镜像里那一份"
    assert "docker exec" in CHECK_SOURCE, "没有真去容器里数文件"
    assert "container_is_running_older_code" in code, "镜像旧了没有单独报出来"
    assert "container_stale" in code and "status = \"FAIL\"" in code, (
        "镜像比仓旧的时候不会让这道门红"
    )


def test_a_stale_image_is_not_lumped_in_with_undeployed_files() -> None:
    """「镜像比仓旧」和「新写的还没发」是两回事，**下一步完全不同**。

    前者要重建镜像（deploy/update.sh），后者只是还没同步。
    报成同一类的话，人会去做错的那一件。
    """
    code = _code_only(CHECK_SOURCE)
    assert "only_local_not_deployed_yet" in code and "container_is_running_older_code" in code
    assert code.count("container_is_running_older_code") >= 1
    # 镜像旧了那条提示必须说清楚要做什么
    assert "重建镜像" in CHECK_SOURCE, "没告诉人镜像旧了该怎么办"


def test_an_unreadable_container_is_not_reported_as_agreement() -> None:
    """**容器里一个文件都没数到，绝不能报成「一样」。**

    容器名写错、docker 没权限、容器没起来——现象都是「零个文件」。
    """
    assert "容器里一个文件都没数到" in CHECK_SOURCE
    assert "查不了，见 container_note" in CHECK_SOURCE, "查不了的时候被当成通过了"


def test_the_deploy_actually_runs_this_check() -> None:
    """**建好了没接上，是这个项目最常见的失败形态；这道检查自己不能是下一例。**

    部署脚本第 8 道门只核了扩展包那一个文件。这道检查补的是其余一百多个，
    但它只有被部署真的调用才算数——放在仓里等人想起来，等于没有。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    code = "\n".join(line for line in deploy.splitlines()
                     if not line.strip().startswith("#"))
    assert "check_production_matches_the_repo.py" in code, (
        "部署脚本没有调用这道检查——只在注释里提到不算"
    )
    # 而且必须能让部署失败，不能只是打印一行好看的。
    tail = code.split("check_production_matches_the_repo.py", 1)[1][:400]
    assert "fail" in tail, "调用了，但对不上的时候不会让部署失败"


def test_the_deploy_names_a_python_that_exists() -> None:
    """调用它用的解释器必须是真存在的那一个。

    第一版写成 `\"${PY}\"`，而这个脚本里根本没有 PY 这个变量——
    `set -u` 会当场报错，部署直接断在最后一步。
    **写的时候顺手抄了另一个脚本的写法，没核这里有没有那个变量。**
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    call_line = next(line for line in deploy.splitlines()
                     if "check_production_matches_the_repo.py" in line
                     and not line.strip().startswith("#"))
    assert "${PY}" not in call_line, "又用了那个不存在的变量"
    assert ".venv/bin/python" in call_line, f"解释器写法可疑：{call_line.strip()!r}"
    assert (ROOT / ".venv/bin/python").exists(), "那个解释器不在"
