"""compose 声明的每个 file-based secret，install.sh 都得建出来（v0.0.0.7）。

## 为什么这条最要命

Docker Compose 对 file-based secret 缺文件是**硬错**：少一个文件，
`docker compose up` 直接起不来，报的还是 Docker 自己的错，
看不出是哪一环没建。而 `start.sh` 每次都跑 `up -d --force-recreate`。

发现时的实况：compose 声明 16 个，install.sh 只建 13 个。
缺的 4 个里有 3 个是本轮加的（两个 OAuth secret + 凭据密钥），
**另一个 github_markdown_token 是既有的**——也就是说一次全新安装
本来就会在 docker compose up 那一步失败。

## 这是同一个形状的第五次

租户审计 → 脱敏面 → 回滚校验 → secret 供给（compose 没挂）→ 现在是
secret 创建（install 没建）。**五次都不是逻辑错，是覆盖面错。**
所以这次不只修，还把比对固化成判据。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _compose_file_secrets() -> set[str]:
    """扫**所有** compose 文件，不只是 compose.yaml。

    只扫一个文件正是本仓反复犯的那个覆盖面错误——
    将来 compose.readers.yaml 加了 file-based secret，只扫主文件就发现不了。
    （现在 readers 那份走 env_file，没有 file secret；这里是防将来。）
    """
    names: set[str] = set()
    files = sorted(ROOT.glob("compose*.yaml"))
    assert files, "一个 compose 文件都没扫到——判据在空转"
    for path in files:
        names |= set(re.findall(
            r"file:\s*\./runtime/secrets/([a-z_][a-z0-9_.]*)",
            path.read_text(encoding="utf-8"),
        ))
    return names


def _install_created_secrets() -> set[str]:
    text = (ROOT / "scripts/install.sh").read_text(encoding="utf-8")
    match = re.search(r"for name in ([a-z_0-9 ]+); do", text)
    assert match, "install.sh 里找不到那个建占位文件的循环——判据失去依附"
    return set(match.group(1).split())


def test_every_compose_secret_file_is_created_by_install() -> None:
    declared = _compose_file_secrets()
    assert len(declared) >= 10, f"只解析出 {len(declared)} 个 secret，判据大概没在查"
    created = _install_created_secrets()
    missing = sorted(declared - created)
    assert not missing, (
        f"compose 声明了这些 file-based secret，但 install.sh 不会创建：{missing}。"
        "Compose 对缺文件是硬错——docker compose up 会直接起不来，"
        "而报的是 Docker 自己的错，看不出是哪一环漏了。"
    )


def test_the_guard_would_notice_a_newly_declared_secret() -> None:
    """先证明它抓得到：模拟 compose 新增一个 install 不认识的 secret。"""
    declared = _compose_file_secrets() | {"some_brand_new_secret"}
    created = _install_created_secrets()
    assert "some_brand_new_secret" in (declared - created), "判据的比对逻辑本身是坏的"


def test_systemd_host_prep_requires_the_same_set() -> None:
    """宿主机那条路（systemd + 独立 secret 目录）不能和 compose 这条漂开。"""
    prep = (ROOT / "scripts/prepare_systemd_host.sh").read_text(encoding="utf-8")
    for name in ("google_oauth_client_secret", "github_oauth_client_secret", "credential_age_identity"):
        assert name in prep, f"prepare_systemd_host.sh 不认识 {name}，宿主机那条路会缺文件"


def test_placeholder_secrets_do_not_pretend_to_be_configured() -> None:
    """空占位必须让应用**明确报未配置**，而不是静默当成配好了。

    这是 INV-NO-SILENT-ZERO 在配置层的同一条：读到空值就说"没配"，
    不要假装能跑然后在第一次真用时才炸。
    """
    from social_archive.credentials import CredentialUnavailable, CredentialVault

    vault = CredentialVault(recipient="", identity_file="")
    try:
        vault.encrypt("x")
    except CredentialUnavailable as exc:
        assert "未配置" in str(exc) or "不能" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("收件人为空时居然没报未配置——空占位会被当成配好了")


def test_every_setting_without_a_default_is_documented_in_env_example() -> None:
    """没有默认值的设置 = 不配就有功能不能用。它必须在 .env.example 里露面。

    有默认值的（页大小、同步间隔之类）不强制写——那是调优旋钮，
    写进模板只会变成噪音。区别就在 os.getenv 有没有第二个参数。

    实测踩到过：本轮加 credential_age 那对时，只把 *_FILE 写进了模板，
    漏了 *_RECIPIENT。两个都要，缺一半就 503，而错误信息只说「未配置」，
    不会告诉你缺的是哪一半。
    """
    config = (ROOT / "src/social_archive/config.py").read_text(encoding="utf-8")
    # os.getenv("X") 无默认 vs os.getenv("X", ...) 有默认
    no_default = set(re.findall(r'os\.getenv\("(SOCIAL_ARCHIVE_[A-Z_0-9]+)"\s*\)', config))
    assert len(no_default) >= 5, f"只解析出 {len(no_default)} 个无默认设置，判据大概没在查"
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(re.findall(r"^#?\s*(SOCIAL_ARCHIVE_[A-Z_0-9]+)=", example, re.M))
    missing = sorted(no_default - documented)
    assert not missing, (
        f"这些设置没有默认值（不配就有功能用不了），但 .env.example 里没有：{missing}。"
        "部署的人无从知道要配它们，而失败表现只是一句「未配置」。"
    )
