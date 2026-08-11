"""代码读的每一个 secret，部署都得真的给它（v0.0.0.7）。

## 这条判据是从一个发布级缺陷里长出来的

T02 加了 OAuth 登录、T05 加了凭据托管，两者都读 `/run/secrets/...` 下的文件，
`.env` 里也写了对应的 `*_FILE` 变量——**看起来配好了**。
但 `compose.yaml` 的 `core-api.secrets` 一个都没加。

后果：`start.sh` 每次都跑 `docker compose up -d --force-recreate core-api`，
重建之后容器里根本没有那些文件。表现是登录 503、已托管的 Cookie 解不开，
而 `.env` 看着完全正常——最难查的那种。

上一轮是靠人肉比对两份清单发现的。这条判据把那次比对固化下来。

## 这是同一个形状的第四次

租户审计 8 张表只数 4 张、脱敏扫描面、回滚校验漏新表，现在是 secret 供给面。
**四次都不是逻辑错，是覆盖面错**——而覆盖面错和「没问题」在报告上一模一样。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 这些不是由 compose 供给 Core 的，各有原因，逐个写明白。
EXEMPT = {
    # 三副本备份的私钥：仅在明确的恢复演练时读取，**刻意不进容器**。
    # 它进了这个 24 小时联网的进程，等于 Core 一旦被攻破就丢掉全部历史备份。
    "SOCIAL_ARCHIVE_AGE_IDENTITY_FILE": "备份私钥，宿主机专用，见 config.py 里 credential_age_* 的说明",
    # 由 systemd 维护任务短时复制，不常驻 Core。
    "SOCIAL_ARCHIVE_GITHUB_TOKEN_FILE": "compose 里以 github_markdown_token 为源、target 改名为 github_token",
    # 可选的自签 CA，用户自己放，没有就走系统信任链。
    "SOCIAL_ARCHIVE_OBSIDIAN_REST_CA_FILE": "可选自签 CA，默认不需要",
}


def _secret_env_names() -> set[str]:
    text = (ROOT / "src/social_archive/config.py").read_text(encoding="utf-8")
    return set(re.findall(r'os\.getenv\("(SOCIAL_ARCHIVE_[A-Z_]*_FILE)"', text))


def _compose_core_secrets() -> set[str]:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    block = text.split("secrets: &core_secrets", 1)[1].split("networks:", 1)[0]
    names = set(re.findall(r"^\s*-\s*([a-z_][a-z0-9_]*)\s*$", block, re.M))
    names |= set(re.findall(r"target:\s*([a-z_][a-z0-9_]*)", block))
    return names


def test_every_secret_file_the_app_reads_is_provisioned_or_explicitly_exempt() -> None:
    env_names = _secret_env_names()
    assert len(env_names) >= 8, f"只扫到 {len(env_names)} 个 *_FILE 设置——判据大概没在查"
    provided = _compose_core_secrets()
    assert provided, "compose.yaml 的 core-api secrets 块没解析出东西"

    missing = []
    for env_name in sorted(env_names):
        if env_name in EXEMPT:
            continue
        # 名字不是逐字对应的：
        #   SOCIAL_ARCHIVE_GOOGLE_CLIENT_SECRET_FILE → google_oauth_client_secret（中间多了 oauth）
        #   SOCIAL_ARCHIVE_KARAKEEP_TOKEN_FILE       → karakeep_api_token       （中间多了 api）
        # 所以按**词的包含**判，不是按子串——子串匹配会把这两对判成缺失
        # （第一版就是这么误报的，是判据错不是供给错）。
        stem_words = set(env_name.removeprefix("SOCIAL_ARCHIVE_").removesuffix("_FILE").lower().split("_"))
        if any(stem_words <= set(name.split("_")) for name in provided):
            continue
        missing.append(env_name)
    assert not missing, (
        f"代码会读这些 secret，但 compose.yaml 没把它们挂给 core-api：{missing}。"
        "重建容器后文件不存在，而 .env 里那几个 *_FILE 变量看着完全正常——"
        "表现是登录 503 或凭据解不开，最难查的那种。"
    )


def test_the_backup_identity_is_not_mounted_into_core() -> None:
    """备份私钥**必须**留在宿主机。

    它进了 Core，「备份通道只有公钥」这条性质就悄悄作废：
    Core 一旦被攻破，攻击者拿到的不只是当前凭据，而是全部历史备份。
    """
    block = (ROOT / "compose.yaml").read_text(encoding="utf-8").split(
        "secrets: &core_secrets", 1)[1].split("networks:", 1)[0]
    for banned in ("age_identity", "age_private", "backup_identity"):
        # credential_age_identity 是另一对密钥，允许；备份那把不允许
        for line in block.splitlines():
            name = line.strip().lstrip("- ").strip()
            if name == banned or (banned in name and not name.startswith("credential_")):
                raise AssertionError(f"备份私钥被挂进 Core 了：{name}")


def test_credential_key_is_separate_from_the_backup_key() -> None:
    """T05 当时把类分开了，却仍共用同一个 identity 设置——那是分了一半。"""
    from social_archive.config import Settings

    fields = Settings.__dataclass_fields__
    assert "credential_age_identity_file" in fields
    assert "credential_age_recipient" in fields
    api = (ROOT / "src/social_archive/api.py").read_text(encoding="utf-8")
    assert "settings.credential_age_identity_file" in api
    assert "identity_file=settings.age_identity_file" not in api, (
        "凭据金库又用回了备份私钥"
    )


def test_env_example_documents_the_new_secret_paths() -> None:
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    for name in ("SOCIAL_ARCHIVE_GOOGLE_CLIENT_SECRET_FILE",
                 "SOCIAL_ARCHIVE_GITHUB_CLIENT_SECRET_FILE",
                 "SOCIAL_ARCHIVE_CREDENTIAL_AGE_IDENTITY_FILE"):
        assert name in env, f".env.example 没写 {name}，部署时没人知道要配它"
    assert "secret 只走 runtime/secrets 文件，永不进 .env" in env


def test_systemd_host_prep_creates_the_same_secret_files() -> None:
    """宿主机预检要求的 secret 集合，必须覆盖 compose 声明的全部。

    这条原先是 `assert "google_oauth_client_secret" in prep` 那样的**文本抽查**
    ——脚本里写着那个名字就算数。于是脚本手写的十五个名字与 compose 的十九个
    差了四个，它一直是绿的。

    脚本改成从 compose 现读之后，文本抽查连"名字在不在文件里"都不成立了，
    正好逼出正确写法：**比对集合，不比对文本。**
    """
    import re

    prep = (ROOT / "scripts/prepare_systemd_host.sh").read_text(encoding="utf-8")
    assert "compose*.yaml" in prep, "宿主机预检不再从 compose 推导 secret 清单"
    declared = set()
    for path in sorted(ROOT.glob("compose*.yaml")):
        declared |= set(re.findall(
            r"file:\s*\./runtime/secrets/([a-z_][a-z0-9_.]*)",
            path.read_text(encoding="utf-8"),
        ))
    assert len(declared) >= 10, f"只解析出 {len(declared)} 个 secret，判据大概没在查"
    # 这几个是本轮明确要求覆盖到的，单独点名，免得集合比对因两边同时漏而假绿。
    for name in ("google_oauth_client_secret", "github_oauth_client_secret",
                 "credential_age_identity", "instagram_session",
                 "x_oauth_token", "reddit_oauth_token"):
        assert name in declared, f"compose 里没有 {name}，宿主机预检也就不会要求它"
