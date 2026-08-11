"""对外说的隐私边界，必须和产品实际做的一致（v0.0.0.7 / T05 · T06）。

## 发现经过

清点每条不变量有几个机器守卫时看到 INV-NO-PASSWORD 只有一个。顺着去看
`/v1/extension/bootstrap` 的 privacy 段，发现它回的是三个**写死的字面量**：

    "cookie_custody": False,
    "password_custody": False,
    "user_triggered_capture_only": True,

第一条从 v0.0.0.7 的 T05/T06 起就是**假的**——产品确实在托管 X / Instagram /
YouTube 的登录状态，读该域 Cookie、转 Netscape 格式、**加密上传**（这正是
docs/ZERO_BARRIER_UX.md 里写明的设计）。而 test_extension_api 逐字断言了
那个字典，也就是说：**一句错的事实，由一盏绿灯守着。**

顺着同一条线看用户真正会读到的地方，安装页上写着：

    「隐私边界：插件不会把密码、Cookie 或浏览器登录状态交给服务器。」

这句话是用户决定要不要装插件时读的最后一句话，而它对西方三源是反的。

## 这条判据守什么

守的不是措辞，是**两组平台的区别有没有被如实说出来**：

  · 国内四源：Cookie 一步都不出浏览器（INV-DOMESTIC-COOKIE-STAYS）
  · 西方三源：加密后托管在自己的服务器上，可一键撤销
  · 两者都不碰密码（INV-NO-PASSWORD）

这个区别本来就是这个产品的设计，不是需要含糊过去的东西。
"""

from __future__ import annotations

from pathlib import Path

from social_archive.credentials import CUSTODIAL_PLATFORMS, DOMESTIC_PLATFORMS

ROOT = Path(__file__).resolve().parents[2]
INSTALL_PAGE = ROOT / "apps/pwa/extension-install.html"

# 曾经写在安装页上的那句话。逐字钉住，防止哪天被"顺手改回去"。
THE_SENTENCE_THAT_WAS_FALSE = "插件不会把密码、Cookie 或浏览器登录状态交给服务器"


def page() -> str:
    return INSTALL_PAGE.read_text(encoding="utf-8")


def test_the_product_does_custody_cookies_so_do_not_say_otherwise() -> None:
    """前提先立住：托管清单非空，就不能对外说"不交给服务器"。"""
    assert CUSTODIAL_PLATFORMS, "托管清单空了的话这条判据要重写，而不是删掉"
    assert THE_SENTENCE_THAT_WAS_FALSE not in page(), (
        "安装页又说回了「不会把 Cookie 交给服务器」，而产品确实在托管 "
        f"{sorted(CUSTODIAL_PLATFORMS)} 的登录状态"
    )


def test_the_page_still_promises_no_password() -> None:
    """INV-NO-PASSWORD 这一半是真的，改文案时不能把它一起删掉。"""
    text = page()
    assert "密码" in text and "永远不会" in text


def test_both_groups_are_named_so_the_difference_is_visible() -> None:
    """国内四源与西方三源的处理方式不同，两组都要点名。

    只说"有些平台不上传"是含糊；用户要能对着自己用的平台查到答案。
    """
    text = page()
    # 显式写死展示名。用 .capitalize() 猜会把 YouTube 猜成 Youtube——
    # 第一版就是这么错的，判据报红而文案其实是对的。
    labels = {
        "xiaohongshu": "小红书", "douyin": "抖音", "bilibili": "B站", "kuaishou": "快手",
        "x": "X", "instagram": "Instagram", "youtube": "YouTube",
    }
    missing = sorted(labels[p] for p in DOMESTIC_PLATFORMS | CUSTODIAL_PLATFORMS
                     if labels[p] not in text)
    assert not missing, f"这些平台没在隐私说明里点名：{missing}——用户查不到自己的平台怎么处理"


def test_the_page_says_it_is_encrypted_and_revocable() -> None:
    """托管这件事说出口的同时，必须把两个约束一起说：加密、可撤销。

    只说"会上传"是吓人；只说"上传"不说"能撤销"，撤销那颗按钮就白做了。
    """
    text = page()
    assert "加密" in text
    assert "撤销" in text


def test_the_page_no_longer_describes_the_removed_pairing_step() -> None:
    """T03 已经把配对码整条链路删掉，安装页却还写着"完成一次性配对"。

    照着做的人会去找一个不存在的输入框，然后以为是自己弄错了——
    **而没有任何东西会报错**。
    """
    assert "一次性配对" not in page()
