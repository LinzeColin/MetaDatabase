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
