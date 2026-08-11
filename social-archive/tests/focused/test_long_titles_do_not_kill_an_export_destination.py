"""一个太长的标题，让 79 条内容再也没导出过（v0.0.0.7 / INV-REAL-USABLE）。

2026-08-03T17:23 生产上实测：

    [Errno 36] File name too long:
    '/var/lib/social-archive/exports/markdown/douyin/.迈特威四…'

根因：`safe_slug` 按**字符**截到 120，而文件系统的上限是 255 **字节**。
一个 120 字的中文标题在 UTF-8 下是 360 字节。

后果不止丢一条。那次失败把整个 markdown 目的地降级成 needs_user_action，
之后每一条导出都被授权闸门挡下：

    destination_receipt:  markdown done 110 / failed 4
    content 193 条，而 markdown 回执只覆盖 114 条 —— **79 条从没导出过**
    destination_state:    last_error_code = DESTINATION_PROBE_REQUIRED
    界面显示：             「目的地尚未完成主动连接检查或授权已失效；请先点击『检查连接』。」

**给用户看的原因完全指错了方向**，而且照它做也修不好——下一个长标题会再炸一次。
"""

from social_archive.utils import SLUG_BYTE_BUDGET, safe_slug

# 生产上炸掉的那条是抖音的长中文标题。这里用同样的形状。
LONG_CHINESE = (
    "迈特威四驱越野房车穿越无人区实录第一集从北京出发一路向西"
    "经过内蒙古甘肃青海新疆最终抵达帕米尔高原全程一万两千公里"
    "沿途记录了戈壁沙漠雪山湖泊以及所有遇到的人和事"
)


def test_a_long_chinese_title_fits_in_a_filename() -> None:
    slug = safe_slug(LONG_CHINESE, "fallback")
    # 调用方拼的是 f"{slug}-{id[-8:]}.md"，atomic_write 再拼 f".{name}.{8位随机}"
    final = f"{slug}-abcdef12.md"
    temp = f".{final}.XXXXXXXX"
    assert len(temp.encode("utf-8")) <= 255, (
        f"临时文件名 {len(temp.encode('utf-8'))} 字节，超过文件系统对单个分量的 255 字节上限"
    )


def test_truncation_is_by_bytes_not_characters() -> None:
    """按字符截是这个 bug 的根因。"""
    slug = safe_slug("中" * 200, "fallback")
    assert len(slug.encode("utf-8")) <= SLUG_BYTE_BUDGET
    # 按字符截的话，200 个中文截到 120 字仍然是 360 字节
    assert len(slug.encode("utf-8")) < 360


def test_truncation_never_splits_a_character() -> None:
    """在字节边界上截，可能正好切在一个多字节字符中间。"""
    for length in range(1, 240):
        slug = safe_slug("啊" * length, "fallback")
        slug.encode("utf-8").decode("utf-8")  # 切坏了这里就抛
        assert "�" not in slug, "截出了替换字符——说明切在了字符中间"


def test_short_titles_are_untouched() -> None:
    assert safe_slug("短标题", "fallback") == "短标题"


def test_an_empty_title_falls_back() -> None:
    assert safe_slug("", "cnt_123") == "cnt_123"
    assert safe_slug("///", "cnt_123") == "cnt_123"


def test_ascii_titles_still_get_a_generous_budget() -> None:
    """英文标题一个字符一个字节，180 字节就是 180 个字符——比原来的 120 更宽。"""
    slug = safe_slug("a" * 400, "fallback")
    assert len(slug) == SLUG_BYTE_BUDGET


# ——— 第二半：单条内容的问题不该拖垮整个目的地 ———

import errno

from social_archive.destinations import DestinationRegistry


def test_a_name_too_long_is_this_items_problem_not_the_destinations() -> None:
    """目的地本身好得很：出错那一秒之前它刚成功写了 110 个文件。

    坏的是这一条内容的名字。而旧代码把它算进「目的地健康度」，
    于是之后每一条新内容都被授权闸门挡下。
    """
    too_long = OSError(errno.ENAMETOOLONG, "File name too long")
    assert DestinationRegistry._is_item_scoped_failure(too_long) is True


def test_every_other_os_error_still_degrades_the_destination() -> None:
    """**只放行 ENAMETOOLONG 这一种。**

    权限、磁盘满、只读文件系统、IO 错误——这些确实意味着目的地不健康，
    必须继续降级。放宽这里等于把真正的故障藏起来。
    """
    for code in (errno.EACCES, errno.ENOSPC, errno.EROFS, errno.EIO, errno.ENOENT):
        assert DestinationRegistry._is_item_scoped_failure(OSError(code, "boom")) is False, (
            f"errno {code} 被当成了单条内容的问题——真正的目的地故障会被藏起来"
        )
    assert DestinationRegistry._is_item_scoped_failure(ValueError("bad config")) is False


def test_the_failure_path_actually_consults_that_distinction() -> None:
    """判据钉在**真正的调用**上，不只是「这个名字出现过」。

    第一版写的是 `"_is_item_scoped_failure" in source`。反证时把
    `if not self._is_item_scoped_failure(exc):` 换成 `if True:` ——
    **判据照样绿**。因为上一行的注释里还写着那个名字。

    这是本会话第五次被自己写的注释骗过：注释里提到一个标识符，
    被当成了对它的引用。所以先剥注释，再找调用形态。
    """
    import inspect

    source = inspect.getsource(DestinationRegistry._record_export_failure)
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    assert "self._is_item_scoped_failure(" in code, "分类函数写了却没人调"
    guard_at = code.index("self._is_item_scoped_failure(")
    state_at = code.index("upsert_destination_state")
    assert guard_at < state_at, "先改了目的地状态才判断，等于没判断"
