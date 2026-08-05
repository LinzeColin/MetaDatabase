"""部署脚本不许再犯 2026-08-04 那次的错（v0.0.0.7 / T18）。

那次的经过：为了让 rsync 写得进去，我现敲了一条

    sudo chown -R ubuntu:ubuntu /opt/social-archive

它把 runtime/secrets/ 下每个密钥的属组从 10001（socialarchive-secrets）
改成 1000。Core 容器跑在 uid 10001，密钥是 0640——属组一变就一点权限都不给，
`/v1/accounts` 之类每一条要鉴权的路由全变 500。

**而 /health 全程 200，容器一直 healthy。** 健康检查不读密钥。

这个失效模式仓库里早写着（scripts/prepare_systemd_host.sh:205
「只给前者，容器 /health 照样 200 而业务路由一律 401」）。我读过那句话，
还是踩了——因为**部署路径没被固化**，经验只存在于注释里，拦不住现敲的命令。

所以这里守的不是"别写错某一行"，是**那条路径本身必须存在，且带着这三道闸**。
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts/deploy_to_production.sh"


def code_only(text: str) -> str:
    """剥掉注释。事故说明里必须能引用 `chown -R`，那是说明不是命令。"""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def test_there_is_a_deploy_script_at_all() -> None:
    """真正的根因是**此前根本没有部署脚本**，每次都现敲 ssh。"""
    assert DEPLOY.is_file(), "没有部署脚本——那就没有任何能守住的规矩"


def test_it_never_recursively_chowns() -> None:
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "chown -R" not in code, (
        "部署脚本里出现了递归 chown。写不进去就定点 sudo chown 那一个路径，"
        "不要对着整棵树做大扫除——那正是把密钥属组改坏的那一下。"
    )


def test_it_measures_the_secret_invariant_on_both_sides_of_the_deploy() -> None:
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "secret_fingerprint" in code, "没有量密钥属主/权限的手段"
    assert code.count("secret_fingerprint") >= 3, (
        "密钥不变量必须**部署前后各量一次**并比对；只量一次等于没量"
    )
    assert '"$BEFORE" != "$AFTER"' in code, "量了却不比对"
    assert "10001" in code, "没有钉住 socialarchive-secrets 的 gid（10001）"


def test_acceptance_hits_an_authenticated_route_not_just_health() -> None:
    """那 6 分钟就是被 /health 的 200 骗过去的。"""
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "/v1/accounts" in code, "验收没打任何要鉴权的路由"
    assert "Authorization: Bearer" in code, "验收没带凭据——那还是在测 /health 那一类"
    health_at = code.index("/health")
    auth_at = code.index("/v1/accounts")
    assert health_at < auth_at, "顺序应是先 /health 再打鉴权路由"


def test_it_keeps_a_rollback_image_and_prints_the_rollback_command() -> None:
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "social-archive/core:rollback" in code, "上线前没给正在跑的镜像留回滚标签"
    assert code.count("social-archive/core:rollback") >= 3, (
        "回滚标签要打、失败时要在报错里给出回滚命令、成功后也要把命令打出来"
    )


def test_rsync_does_not_delete_and_does_not_touch_runtime_or_env() -> None:
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    rsync = code.split("rsync ", 1)[1].split("|| fail", 1)[0]
    assert "--delete" not in rsync, (
        "带 --delete 的第一版试图删掉远端我自己留的 .env.pre-* 备份"
    )
    for keep in ("runtime/", ".env", ".venv", ".git"):
        assert f"--exclude '{keep}'" in rsync, f"没有排除 {keep}——那是数据/密钥/远端环境"


def test_it_also_checks_the_group_can_read_not_just_who_owns_it() -> None:
    """属组对了还不够，权限位也要给组。

    2026-08-04 实测抓到的：instagram_session 的属组是对的（10001），
    而权限是 **0600**——组权限为零。cli-tools 跑在 uid 10002 / gid 10001，
    于是它读不到自己的密钥，**Instagram 从来就没能工作过**。

    只查属组的话，这个文件在上一关是"合格"的。
    """
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "BAD_MODE" in code, "只查了属组，没查组读位"
    assert "10002" in code, "没写清 cli-tools 靠组权限读（uid 10002 不是属主）"
    # 判据要看 mode 的中间那一位
    assert "[4567]" in code, "组读位的判据不在了——写法变了就要跟着重写"


def test_it_refuses_to_build_when_the_disk_is_tight() -> None:
    """每次部署都造一个 1GB 的镜像，旧的变孤儿。

    2026-08-04 我一天部署了十几次，生产盘从 8.3G 可用掉到 3.0G（93%），
    紧接着 /v1/accounts 报过一次
    `sqlite3.OperationalError: unable to open database file`
    ——SQLite 建不出 -wal/-shm 时就是这句话。**复现不了**（清完盘之后
    连打三次全 200），所以磁盘只是最合理的怀疑，不是已证实的根因。

    但门槛该有：盘紧的时候不许再往上叠一个 1GB 的镜像。
    """
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "FREE_KB" in code, "部署前不看磁盘"
    # **尺子不能向上取整。**
    # 2026-08-05 对着生产同时跑了两种量法：真实可用 4.84G，
    # `df -BG` 读到 5G → 这道「至少 5G」的门当场放行；改成按 KB 精确比较后拦下。
    # 最坏情况虚报接近 1G（4.01G 也报成 5G），而**虚报的方向恰好是不安全那一侧**：
    # 它存在的理由就是「盘紧的时候别再叠一个 1GB 的镜像」，却偏偏在最紧时说谎。
    assert "df -k --output=avail" in code, "磁盘量法不是精确的 KB"
    assert not re.search(r"df -B[A-Z][^|]*--output=avail", code), (
        "又用回了向上取整的块单位——4.01G 会被报成 5G，门在最需要它的时候放行"
    )
    # 阈值 2026-08-05 做成了可配（默认仍是 5），好让「不够→回收→重量→决定」
    # 那一串能在生产真的快满之前被验一次。判据跟着钉两件事：
    # 有比较、且默认值没被人顺手调低。
    assert '"$FREE_KB" -lt "$MIN_FREE_KB"' in code, "没有阈值，或者写法变了、判据要跟着改"
    assert 'MIN_FREE_GB="${SOCIAL_ARCHIVE_DEPLOY_MIN_FREE_GB:-5}"' in code, (
        "默认门槛不是 5 了——可配是为了能验，不是为了把门放宽"
    )
    # 回收建议必须是安全的那一种
    assert "dangling=true" in code, "没有给出只删悬空镜像的回收办法"
    assert "docker system prune" in code, "没有点名那条危险命令"
    warn = code.split("docker system prune", 1)[0][-260:]
    assert "不要用" in warn, (
        "提到了 docker system prune 却没说别用它——这台机器还跑着别人的项目"
    )


def test_it_notices_when_the_installed_systemd_units_have_drifted() -> None:
    """rsync 只同步 /opt/social-archive，装着的 unit 在 /etc/systemd/system。

    2026-08-04 实测：我在仓里给 social-archive-backup.service 加了第二条
    ExecStart（备份运行库），部署、daemon-reload、systemctl start 全都
    `Result=success`——**而跑的还是旧的那一条**。装着的 unit 从来没被更新过。
    差一点就把「备份跑通了」写进证据。
    """
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    assert "/etc/systemd/system/" in code, "部署时不看装着的 unit 是不是旧的"
    assert "DRIFT" in code, "没有漂移检查"
    # 只报不自动装：unit 以 root 跑，自动安装的爆炸半径太大
    assert "sudo cp /etc/systemd" not in code and "install -m" not in code, (
        "部署脚本自己去装 unit 了——那是 root 权限的东西，应当由人来敲"
    )
    drift_at = code.index("DRIFT")
    build_at = code.index("docker compose build")
    assert drift_at < build_at, "构建都跑完了才发现 unit 是旧的"


def test_the_deploy_cleans_up_the_image_it_orphaned_itself() -> None:
    """**谁开的谁收。** 每成功部署一次就留下一个 1GB 的悬空镜像。

    :rollback 只留一层（那是设计），所以这一次的部署会把上一次的回滚点顶掉，
    那个镜像随即变成悬空。原来只有「磁盘不够」那条路才回收，于是它
    **一直攒到把门顶住为止**——2026-08-05 实测 7.31G → 部署一次 → 5.19G，
    两次就顶到 5G 门槛。

    那天为了腾地方，最后是让 Owner 去裁定删同机别的项目的缓存。
    **而真正该收的是我们自己每次留下的这一个。**
    """
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    # **钉的是那条命令，不是步骤标题。**
    # 第一版写的是 `assert "10)" in code`——把步骤改名成「10) 什么都不收」
    # 它照样绿。判据钉在编号上等于没钉。
    tail = code.split("三份一致")[-1]
    assert "dangling=true" in tail and "docker rmi" in tail, (
        "**三份一致之后没有回收自己留下的悬空镜像**——"
        "每成功部署一次就攒一个 1GB，攒到把磁盘门顶住为止"
    )
    assert "docker rmi" in tail.split("dangling=true")[-1], (
        "列出来了却没删——列表本身不省地方"
    )


def test_every_dangling_sweep_is_fenced_to_our_own_label() -> None:
    """**这台机器还跑着别人的项目。**

    memory-atlas / gatus / coolify 都在同一个 docker 里。任何一次
    `docker rmi $(docker images -f dangling=true -q)` 都会连他们的一起删掉，
    而悬空镜像对他们可能正是回滚点。

    所以判据钉的不是「这一处写对了」，是**每一处都必须写对**：
    凡是拿 dangling 列表去删的，同一条命令里必须有我们自己的标签。
    """
    code = code_only(DEPLOY.read_text(encoding="utf-8"))
    for line in code.splitlines():
        if 'dangling=true' not in line:
            continue
        # 只列出来给人看的不算（没有 -q，也没喂给 rmi）
        if "-q" not in line:
            continue
        assert "label=com.socialarchive.project" in line, (
            "**这一行会把别的项目的悬空镜像一起删掉**——"
            f"拿 dangling 列表去删，必须同时按我们自己的标签过滤：\n    {line.strip()}"
        )
