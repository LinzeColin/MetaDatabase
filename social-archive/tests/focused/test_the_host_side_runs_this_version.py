"""主机那半边跑的必须也是这一版（v0.0.0.7 / T18）。

2026-08-05 实测：容器里的 Core 报 0.0.0.7，而**主机 venv 里装着的是 0.0.0.5**
——落后两个版本。site-packages 里放的是一份拷贝，21 个文件与仓里不同，
account_sync / auth / credentials / platform_payloads 等**六个模块根本不存在**。

而备份、复制、私有库同步、状态发布**四个 timer 全跑在主机 venv 上**。
症状完全静默：systemctl 报 success，备份 PASS，只有去对字段才发现
发布出来的状态页少了一个这一版才有的字段。

判据守两件：部署要检查这件事；以及包元数据的版本别再自己漂。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_the_package_metadata_version_matches_the_version_file() -> None:
    """pyproject 的 version 一直停在 0.0.0.6，而 VERSION 是 0.0.0.7。

    它决定 `pip install` 记下来的版本号——主机上 `pip show` 因此一直报错的数。
    这种「两个地方各写一份版本」正是漂移的温床。
    """
    declared = re.search(r'^version = "([^"]+)"',
                         (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    assert declared, "pyproject.toml 里找不到 version"
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    assert declared.group(1) == expected, (
        f"pyproject 写着 {declared.group(1)}，VERSION 写着 {expected}——两份版本号又漂了"
    )


def test_the_deploy_checks_the_host_venv_is_not_a_stale_copy() -> None:
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "主机 venv" in deploy, "部署脚本不检查主机 venv——四个 timer 可能一直跑旧代码"
    assert "social_archive.__file__" in deploy, "没有去看装着的那份到底是哪个文件"
    assert "pip install -e . --no-deps" in deploy, (
        "发现漂移之后没有修；只报不修的话，下一个人还得自己去敲那行命令"
    )
    assert "social_archive.__version__" in deploy, "没有比对版本号"


def test_install_script_still_uses_an_editable_install() -> None:
    """生产之所以会漂成一份拷贝，就是因为它偏离了 install.sh 写的做法。

    这条判据钉住 install.sh 本身别改成非 editable——一改，
    以后每次同步源码都要重装一次，而没有人会记得。
    """
    install = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    assert "pip install -e" in install, (
        "install.sh 改成了非 editable 安装——那样 rsync 完源码，主机那半边还是旧的"
    )


def test_the_deploy_also_checks_the_other_container() -> None:
    """部署只重建 core-api，而 cli-tools 是另一个镜像。

    改了 sidecars/cli-tools/ 而不重建，跑着的就一直是旧的——**而 compose
    会照常报 Healthy**。这与「主机 venv 落后两个版本」是同一族，换了个地方藏。

    钉住三件：它会去比、比的是量出来的那个路径、不同的时候会真的修。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "cli-tools" in deploy, "部署完全不管另一个容器"
    assert "/worker/server.py" in deploy, (
        "比的不是量出来的那个路径——容器里还有两个同名的 server.py（标准库里的），"
        "靠 find|head 早先差点比错对象"
    )
    assert "docker compose build cli-tools" in deploy, "发现落后了却不重建"
    assert "Dockerfile.built" in deploy, (
        "只比 server.py 的话，「只改 Dockerfile 不改 server.py」那种改动看不出来"
    )
    dockerfile = (ROOT / "sidecars/cli-tools/Dockerfile").read_text(encoding="utf-8")
    assert "COPY Dockerfile /worker/Dockerfile.built" in dockerfile, (
        "镜像里没有 Dockerfile 的副本，那道门就没得比"
    )
    assert "这不是通过" in deploy, (
        "容器没在跑时应当明说这是跳过；把跳过印成通过，正是本项目一直在防的那种谎"
    )


def test_the_rollback_point_is_pinned_before_the_build_and_verified_after() -> None:
    """**回滚点是出事那天唯一能回的地方，它自己不能悄悄失效。**

    2026-08-05 实测：第 3 步只记下镜像 ID、等构建完再打标——而构建会把同名
    旧镜像收走，等到打标时 `docker tag <旧ID>` 报 No such image。那一行当时
    写成 `docker tag … && printf …`，失败被 && 短路吞掉，**一声不吭**。
    于是当天十几次部署，:rollback 一直停在很多版之前的镜像上，
    而每次结尾还照印那行「回滚一行命令」。

    三条一起钉：构建前用临时标签钉住、失败要 fail 而不是静默、
    转正之后回头核对它指向的确实是部署前那个镜像。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in deploy.splitlines() if not l.lstrip().startswith("#"))
    assert "ROLLBACK_CANDIDATE" in code, "构建前没有把当前镜像钉住，构建会把它收走"
    pin = code.split("ROLLBACK_CANDIDATE}'\"", 1)
    assert "|| fail" in code.split("docker tag", 1)[1][:400], (
        "打标失败会被静默吞掉——那正是 :rollback 停在旧版上十几次没人发现的原因"
    )
    assert 'ROLLBACK_ID' in code and '"$ROLLBACK_ID" == "$IMAGE_BEFORE"' in code, (
        "转正之后没有回头核对回滚点指向的是不是部署前那个镜像"
    )
    assert "&& printf '  回滚点已定" not in code, (
        "又写回 `cmd && printf` 了——失败会被短路吞掉，什么都不说"
    )


def test_the_disk_gate_only_reclaims_our_own_images() -> None:
    """**这台机器还跑着别人的项目。**

    磁盘门今天拦了两次，两次都要人手工回收——自动化是对的，但自动化的
    边界必须卡死：只回收**带我们自己标签的**悬空镜像。

    `docker system prune` 是明确禁止的（脚本里早就写着）；而「删掉所有悬空
    镜像」看着温和，实际是在动别人的东西——别的项目可能正准备给某个悬空
    镜像重新打标。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in deploy.splitlines() if not l.lstrip().startswith("#"))
    assert "label=com.socialarchive.project=social-archive" in code, (
        "自动回收没有按标签筛——那会删到别的项目的悬空镜像"
    )
    # **禁的是「用它」，不是「提它」。**
    # 脚本里唯一一处 system prune 在那句警告文案里（「**不要用** docker system
    # prune」）——把提及也禁掉，判据就会红在一句正确的警告上。
    # 这和早先「注释里出现 PASS 就报错」是同一种过严。
    mentions = [l.strip() for l in code.splitlines() if "system prune" in l]
    for line in mentions:
        assert "不要用" in line, f"这一行像是在真的执行 system prune：{line[:90]}"
    assert mentions, "那句「不要用 docker system prune」的警告没了"
    # 收不够就得中止，不能默默继续构建
    # 钉的是**行为**，不是那个数字：门槛后来做成可配的了（为了能验那一串），
    # 消息里的 5G 变成了 ${MIN_FREE_GB}G。判据锚在数字上就会红在一次正确的改动上。
    assert code.count("可用空间不足 ${MIN_FREE_GB}G，拒绝构建") == 1, "回收不够时不再中止了"


def test_both_images_carry_the_label_the_gate_filters_on() -> None:
    """筛条件和盖的戳必须对上——对不上就永远回收不到任何东西，

    而那种失败是**静默**的：门会说「没有带我们标签的悬空镜像可收」，
    听起来像「已经很干净了」。
    """
    for relative in ("Dockerfile", "sidecars/cli-tools/Dockerfile"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert 'LABEL com.socialarchive.project="social-archive"' in text, (
            f"{relative} 没盖标签，它造出来的悬空镜像永远收不掉"
        )


def test_the_disk_threshold_defaults_to_five_and_can_be_raised_for_testing() -> None:
    """门槛做成可配的，**唯一的理由是它必须能被验**。

    「空间不够 → 自动回收 → 重新量 → 还不够就中止」这一串，门槛写死的话
    只能等生产真的快满了才跑得到——而那是最不该拿来做第一次验证的时刻。

    默认值必须还是 5：可配是为了验，不是为了让人随手调低把门放宽。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert 'MIN_FREE_GB="${SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB:-5}"' in deploy, (
        "门槛不可配就没法验那一串；或者默认值被改掉了"
    )
    code = "\n".join(l for l in deploy.splitlines() if not l.lstrip().startswith("#"))
    assert '-lt 5 ' not in code and '-lt 5]' not in code, "还有地方写死 5，改门槛时会漏掉"
    assert "MIN_FREE_KB=$(( MIN_FREE_GB * 1048576 ))" in code, (
        "门槛以 G 配、以 KB 比，中间的换算必须在场——少了它就是拿 G 去比 KB"
    )
    # **不写死比较次数。**
    #
    # 原来这里断言「正好 2 次」。2026-08-07 加了第二段回收（收掉我们自己上一个
    # 版本的镜像）之后它就红了——而那次改动**恰恰是对的**：多一段回收就该多一次
    # 重量、多一次比较。写死次数的判据在这里守不住任何东西，只是拦住了加回收。
    #
    # 它真正要守的是两件事，直接写出来：
    #   · 每一处比较都用同一个门槛（不许有人在某一段里写死数字）
    #   · **每一次「回收完再比一次」之前都重新量过**——少了重量那一步，
    #     回收多少都没用，门看的还是回收前那个数。
    lines = code.splitlines()
    compares = [i for i, line in enumerate(lines) if "-lt " in line and "FREE_KB" in line]
    measures = [i for i, line in enumerate(lines) if 'FREE_KB="$(free_kb)"' in line]
    assert len(compares) >= 2, "回收之后必须重新比一次，否则回收了也白回收"
    for index in compares:
        assert '-lt "$MIN_FREE_KB"' in lines[index], (
            f"第 {index} 行的比较没用 $MIN_FREE_KB：{lines[index].strip()}")
    for previous, current in zip(compares, compares[1:]):
        assert any(previous < m < current for m in measures), (
            f"第 {current} 行又比了一次，**中间却没有重新量**——"
            "回收完不重量，门看的还是回收前那个数")


def test_an_aborted_deploy_does_not_leave_a_tag_pinning_a_gigabyte() -> None:
    """**钉住镜像的动作必须排在磁盘门之后。**

    2026-08-05 实测：原来第 3 步就打 :rollback-candidate，而部署可能在第 4 步
    （磁盘不够）中止——那个标签留下来，死死钉住一个 1.06GB 的镜像，
    它因此永远不会变成悬空、永远收不掉。于是**「磁盘不够 → 中止 → 又多钉一个」
    自己喂自己**。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    code = "\n".join(l for l in deploy.splitlines() if not l.lstrip().startswith("#"))
    disk_gate = code.index("构建前先看磁盘")
    pin = code.index("ROLLBACK_CANDIDATE}'\"")
    assert pin > disk_gate, (
        "又把「钉住镜像」排到磁盘门前面了——中止的部署会留下一个钉着 1GB 的标签"
    )


def test_the_disk_advice_does_not_send_you_after_nothing() -> None:
    """悬空镜像可能一个都没有——那时还叫人「回收悬空镜像」就是白跑一趟。

    这和我今天在连接器文案上修的是同一种病（下一步指向一个帮不上忙的东西），
    只不过这次在自己的门里。
    """
    deploy = (ROOT / "scripts/deploy_to_production.sh").read_text(encoding="utf-8")
    assert "docker system df" in deploy, "收不够时不摆出真实占用，人无从下手"
    assert "Build Cache" in deploy or "builder prune" in deploy, (
        "没提 Build Cache——实测拦下部署那次悬空是 0 个，占地方的是它"
    )
    assert "由人决定" in deploy, "builder prune 会影响同机别的项目，不能替人决定"
