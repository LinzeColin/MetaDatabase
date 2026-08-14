"""平台身份取自「你连的那个账号」，而不是一个没人设得上的环境变量（v0.0.0.7）。

## 这条是新门抓出来的

`scripts/find_settings_with_no_way_to_set_them.py` 第一次跑报出六项：

    SOCIAL_ARCHIVE_X_USER_ID              registry.py 读它
    SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE     registry.py 读它
    SOCIAL_ARCHIVE_REDDIT_USERNAME        registry.py 读它
    SOCIAL_ARCHIVE_REDDIT_USER_AGENT      registry.py 读它
    SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE registry.py 读它
    SOCIAL_ARCHIVE_INSTAGRAM_USERNAME     registry.py 读它

**六项在 .env.example、compose、部署脚本、文档里一处都没有。** 也就是说：
Owner 把该做的全做对了——部署、登录、连接账号——X / Reddit / Instagram 的
服务端同步仍然一条都取不到，而没有任何东西告诉他还差什么。这是
INV-ZERO-BARRIER 明令禁止的那种「看不见也修不了」的门槛。

而身份这三项**根本不该来自环境变量**：`ConnectorRunRequest.source_account_id`
一直带着已连接账号的 external_account_id 传进 registry.run()，
那三个分支从来没看过它。管子早就通到门口了，就是没接上。

## 为什么还要验形状

浏览器会话连接在拿不到真实账号名时写的是 `browser-session:{platform}`，
Chrome 书签那条固定写 `chrome-bookmarks`。拿这种占位值去请求平台会换来
一个 404，而 404 的文案说的是「接口失败」——**不是**「我们不知道你是谁」。
两者的下一步不一样，就不能合并成一个错。
"""

from __future__ import annotations

import pytest

from social_archive.models import ConnectorRunRequest
from social_archive.registry import ConnectorRegistry


def request_for(external: str | None) -> ConnectorRunRequest:
    return ConnectorRunRequest(source_account_id=external)


@pytest.mark.parametrize(
    ("connector", "external"),
    [("reddit", "spez"), ("x", "44196397"), ("instagram", "my.handle_1")],
)
def test_a_real_handle_from_the_connected_account_is_used(
    connector: str, external: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """连了账号就该用那个账号的身份，不必再去读环境变量。"""
    monkeypatch.delenv("SOCIAL_ARCHIVE_UNSET_FOR_TEST", raising=False)
    got = ConnectorRegistry._account_identity(
        connector, request_for(external), "SOCIAL_ARCHIVE_UNSET_FOR_TEST"
    )
    assert got == external


@pytest.mark.parametrize(
    "placeholder", ["browser-session:reddit", "browser-session:x", "chrome-bookmarks"]
)
def test_placeholder_account_ids_are_not_identities(
    placeholder: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """占位值不是身份。拿它去请求平台换来的是 404，而 404 说的是另一件事。"""
    monkeypatch.setenv("SOCIAL_ARCHIVE_FALLBACK_FOR_TEST", "from-env")
    got = ConnectorRegistry._account_identity(
        "reddit", request_for(placeholder), "SOCIAL_ARCHIVE_FALLBACK_FOR_TEST"
    )
    assert got == "from-env"


def test_wrong_shape_for_the_platform_falls_back_rather_than_being_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """X 的接口用数字 user id。账号里存的是 @handle 时不能硬塞进去。"""
    monkeypatch.setenv("SOCIAL_ARCHIVE_FALLBACK_FOR_TEST", "44196397")
    got = ConnectorRegistry._account_identity(
        "x", request_for("elonmusk"), "SOCIAL_ARCHIVE_FALLBACK_FOR_TEST"
    )
    assert got == "44196397", "把一个非数字的句柄当 X user id 用了"


def test_no_account_and_no_env_means_we_honestly_do_not_know(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """两边都没有就是 None——连接器据此返回 blocked_environment 并说明原因。

    **这一条不许被"兜底成某个默认值"取代**：编一个身份出来，
    换来的是一次看起来正常、实际取到别人（或空）内容的同步。
    """
    monkeypatch.delenv("SOCIAL_ARCHIVE_FALLBACK_FOR_TEST", raising=False)
    assert ConnectorRegistry._account_identity(
        "reddit", request_for(None), "SOCIAL_ARCHIVE_FALLBACK_FOR_TEST"
    ) is None


def test_the_connector_says_who_is_missing_not_just_that_it_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """身份缺失要落到 REDDIT_AUTH_MISSING，而不是一个笼统的接口错误。"""
    from social_archive.connectors.oauth import RedditConnector

    monkeypatch.delenv("SOCIAL_ARCHIVE_REDDIT_USERNAME", raising=False)
    result = RedditConnector(None, "sa-test/1", lambda: "token").fetch("saved")
    assert result.status == "blocked_environment"
    assert result.errors[0]["code"] == "REDDIT_AUTH_MISSING"
    assert result.errors[0]["retryable"] is False, "缺身份不是重试能解决的"


def test_every_identity_variable_is_documented_somewhere_settable() -> None:
    """六个变量都要有一条文档化的设置路径。

    这条判据和 scripts/find_settings_with_no_way_to_set_them.py 是同一件事的
    两个落点：门管住将来新增的，这条钉住这次修好的六个不许再退回去。
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    surface = (root / ".env.example").read_text(encoding="utf-8")
    surface += (root / "compose.yaml").read_text(encoding="utf-8")
    for name in (
        "SOCIAL_ARCHIVE_X_USER_ID",
        "SOCIAL_ARCHIVE_X_OAUTH_TOKEN_FILE",
        "SOCIAL_ARCHIVE_REDDIT_USERNAME",
        "SOCIAL_ARCHIVE_REDDIT_USER_AGENT",
        "SOCIAL_ARCHIVE_REDDIT_OAUTH_TOKEN_FILE",
        "SOCIAL_ARCHIVE_INSTAGRAM_USERNAME",
    ):
        assert name in surface, f"{name} 又变回了「代码读它、没人设得上」"


def test_the_two_new_secrets_are_actually_created_by_install() -> None:
    """compose 声明的 file-based secret 缺文件是硬错，docker compose up 直接起不来。"""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    install = (root / "scripts/install.sh").read_text(encoding="utf-8")
    for name in ("x_oauth_token", "reddit_oauth_token"):
        assert name in install, f"compose 声明了 {name}，install.sh 却不建它"
