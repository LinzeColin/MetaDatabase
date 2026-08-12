"""脱敏器同时犯了两个方向相反的错（v0.0.0.7 / INV-HONEST-EVIDENCE）。

旧版：`(?i)(token|secret|password|cookie|authorization|session)[=: ]+[^\\s,;]+`

**漏。** `Authorization: Bearer eyJhbGciOi….SIG` 里，关键词后面的第一段是
`Bearer`——它把 "Bearer" 这个词遮住，**把真正的 JWT 原样留在日志里**：

    Authorization=<已隐藏> eyJhbGciOiJIUzI1NiJ9.PAYLOAD.SIG

这个函数存在的全部理由就是防这个。

**过。** 分隔符里有一个裸空格，于是中文散文被吃掉：

    Instagram Session 尚未配置          → Instagram Session=<已隐藏>
    缺少 Reddit OAuth token 或 username → 缺少 Reddit OAuth token=<已隐藏> username

**用户最需要的那句解释，被脱敏器吃掉了。** 2026-08-04 生产实测发现的：
修好 Instagram 的密钥权限之后，失败原因显示成 `Instagram Session=<已隐藏>`。
"""

import pytest

from social_archive.utils import redact

JWT = "eyJhbGciOiJIUzI1NiJ9.PAYLOAD.SIG"


@pytest.mark.parametrize("raw", [
    f"Authorization Bearer {JWT}",
    f"Authorization: Bearer {JWT}",
    f"authorization={JWT}",
    "password: hunter2",
    "password hunter2",
    "api_key=sk-live-0123456789abcdef",
    "cookie sessionid=ABCDEF123456",
])
def test_real_secrets_do_not_survive(raw: str) -> None:
    out = redact(raw)
    assert "<已隐藏>" in out, f"整段都没被遮：{out}"
    for leak in (JWT, "hunter2", "sk-live-0123456789abcdef", "ABCDEF123456"):
        assert leak not in out, f"**密钥漏出来了**：{out}"


@pytest.mark.parametrize("raw", [
    "Instagram Session 尚未配置",
    "Instagram Session 权限不安全",
    "缺少 Reddit OAuth token 或 username",
    "登录 token 已过期",
    "Authorization header missing",
])
def test_explanations_survive_intact(raw: str) -> None:
    """用户最需要的那句话不许被脱敏器吃掉。"""
    assert redact(raw) == raw, f"解释被吃了：{redact(raw)}"


def test_it_keeps_the_harmless_parts_of_a_cookie_header() -> None:
    out = redact("set-cookie: sessionid=REALSECRET; Path=/")
    assert "REALSECRET" not in out
    assert "Path=/" in out, "把无害的属性也一起遮了，日志失去可读性"
