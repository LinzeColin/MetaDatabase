"""「我们没做这件事」不许说成「暂时连不上，重试」（v0.0.0.7 / T14）。

## 这个坑踩过两次

第一次：`ACQUISITION_PATH_NOT_INSTALLED`（T03 拆掉取数通道之后的显式失败）
别名成 `SERVER_UNREACHABLE`，于是界面对着一件**永远不可能成功**的事说
「暂时连不上服务器。你的数据没有丢，[ 重试 ]」。Owner 的原话是
「不知道应该怎么操作」。修法记在 `failure_copy._ALIASES` 上面那段说明里。

第二次：`INTERCEPT_PREFIX_UNKNOWN` —— **就写在那段说明下面第四行**，
同样别名成 `SERVER_UNREACHABLE`。它的真实含义是「还没有确认这个平台的
收藏接口地址，这个平台暂时不能同步」，重试一万次也一样。
2026-08-06 发现并移进 `PRODUCT_FAULT_CODES` / `DELIBERATELY_UNALIASED`。

**说明写在旁边没能拦住第二次。** 所以把它变成判据。

## 判据

`PRODUCT_FAULT_CODES` 里的每一个码，落到用户面前的那句话都不能是
「retryable」那一类——那一类的含义是「你自己点一下就可能好」，
而产品缺陷类的含义正相反：**你做什么都没用**。

## 它不管什么

- 不管文案写得好不好听，只管**类别对不对**。
- 不管界面有没有真的把这句话显示出来（那是别的判据的事）。
"""

from __future__ import annotations

from social_archive import failure_copy


def test_no_product_fault_code_resolves_to_a_retryable_sentence() -> None:
    """产品缺陷类的码，不许落到一句让人重试的话上。"""
    wrong: list[str] = []
    for code in sorted(failure_copy.PRODUCT_FAULT_CODES):
        copy = failure_copy.resolve(code)
        if copy is not None and copy.failure_class == "retryable":
            wrong.append(f"{code} → {copy.code}「{copy.template[:34]}」")
    assert not wrong, (
        "**这些码的意思是「我们没做这件事」，落下来的却是一句「重试」**：\n  "
        + "\n  ".join(wrong)
        + "\n重试一万次也一样——把它移出 _ALIASES，或改别名到一条非 retryable 的词条。"
    )


def test_the_two_codes_that_burned_us_are_still_product_faults() -> None:
    """**具体钉住那两个**。

    上面那条是通则；万一有人把某个码从 PRODUCT_FAULT_CODES 里拿出去、
    再别名回 SERVER_UNREACHABLE，通则不会红（它只遍历表里的）。
    这一条盯着这两个名字本身。
    """
    for code in ("ACQUISITION_PATH_NOT_INSTALLED", "INTERCEPT_PREFIX_UNKNOWN"):
        assert code in failure_copy.PRODUCT_FAULT_CODES, (
            f"{code} 被从产品缺陷类里拿出去了。它的含义是「本版本没装这条路」，"
            "任何别名都会变成一句「重试」，而重试永远不会成功。"
        )
        assert failure_copy._ALIASES.get(code) != "SERVER_UNREACHABLE", (
            f"{code} 又被别名回「暂时连不上服务器 [重试]」了——这个坑已经踩过两次。"
        )
