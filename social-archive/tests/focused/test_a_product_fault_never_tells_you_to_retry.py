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
    # **字段名是 kind，不是 failure_class。**
    # 第一版写的是 `copy.failure_class`——那个属性根本不存在，而这条判据
    # 照样绿：产品缺陷类的码大多 resolve() 返回 None，那一支永远没进去过。
    # 反例当时「红了」也是假的，红在 AttributeError 上，不是红在断言上。
    # **一条永远走不到断言的判据，和没有这条判据是一回事。**
    checked = 0
    wrong: list[str] = []
    for code in sorted(failure_copy.PRODUCT_FAULT_CODES):
        copy = failure_copy.resolve(code)
        if copy is None:
            continue                      # 不给别名 = 落到「这是产品的问题」，正是要的
        checked += 1
        if copy.kind == "retryable":
            wrong.append(f"{code} → {copy.code}「{copy.template[:34]}」")
    assert not wrong, (
        "**这些码的意思是「我们没做这件事」，落下来的却是一句「重试」**：\n  "
        + "\n  ".join(wrong)
        + "\n重试一万次也一样——把它移出 _ALIASES，或改别名到一条非 retryable 的词条。"
    )
    # **有别名的那些必须真的被查过。** 全都 resolve 成 None 的话，
    # 上面那个循环一次都没进 if，而判据照样绿——那正是第一版的样子。
    aliased = [c for c in failure_copy.PRODUCT_FAULT_CODES if failure_copy.resolve(c) is not None]
    assert checked == len(aliased), (
        f"该查 {len(aliased)} 个有别名的产品缺陷码，实际只查了 {checked} 个"
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


def test_the_pwa_alias_table_has_not_drifted_from_the_server() -> None:
    """**两张表，各修各的，必然漂开。**

    服务端把 `ACQUISITION_PATH_NOT_INSTALLED` 移出别名表（改成「这是产品的问题」）
    之后，PWA 那一侧**没跟着改**——2026-08-06 实测，它还别名着
    `SERVER_UNREACHABLE`，也就是「暂时连不上服务器，[ 重试 ]」。

    同一个失败码，服务端说「我们的问题」，界面说「重试」。
    这条判据不比对整张表（两侧本来就粗细不同），只钉一件事：
    **服务端认定为产品缺陷的码，界面不许把它别名成别的句子。**
    """
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parents[2] / "apps/pwa/app.js").read_text(encoding="utf-8")
    block = re.search(r"const failureAliases = \{(.*?)\n  \};", app_js, re.S)
    assert block, "PWA 里的 failureAliases 找不到了——判据的射程失效，先修判据"
    body = "\n".join(l for l in block.group(1).splitlines() if not l.lstrip().startswith("//"))
    aliased_in_pwa = set(re.findall(r"^\s*([A-Z_]+)\s*:", body, re.M))

    drifted = sorted(aliased_in_pwa & failure_copy.PRODUCT_FAULT_CODES)
    assert not drifted, (
        "**服务端认定这些是产品缺陷，而界面把它们别名成了别的句子**："
        + ", ".join(drifted)
        + "。从 apps/pwa/app.js 的 failureAliases 里删掉，让它落到那句"
          "「这是产品的问题…请联系我们」的兜底上。"
    )


# **两侧只准许有意的差异，而现在一条都没有。**
# 有意让某个码只出现在一侧时，写进这里并说清为什么；空着就是「必须完全一致」。
ONE_SIDED_ON_PURPOSE: dict[str, str] = {}


def test_both_alias_tables_say_exactly_the_same_thing() -> None:
    """服务端与界面的失败码别名表必须**逐条一致**。

    上面那条只钉「产品缺陷类」这一小块。而漂开这件事不挑类别——
    2026-08-06 实测漂开的那两条恰好都在那一块里，纯属运气。

    这条把整张表钉上：**同一个失败码，两个界面不许给用户两句不同的话。**
    实测两侧各 39 条、逐条相同，所以这个不变量今天是真的成立的，
    不是一句愿望。
    """
    import re
    from pathlib import Path

    app_js = (Path(__file__).resolve().parents[2] / "apps/pwa/app.js").read_text(encoding="utf-8")
    block = re.search(r"const failureAliases = \{(.*?)\n  \};", app_js, re.S)
    assert block, "PWA 里的 failureAliases 找不到了——判据的射程失效，先修判据"
    body = "\n".join(l for l in block.group(1).splitlines() if not l.lstrip().startswith("//"))
    pwa = dict(re.findall(r'^\s*([A-Z_]+)\s*:\s*"([A-Z_]+)"', body, re.M))
    assert len(pwa) >= 20, f"只解析出 {len(pwa)} 条别名——**解析失败和「两边一致」长得一样**，先修判据"

    server = dict(failure_copy._ALIASES)
    for code in ONE_SIDED_ON_PURPOSE:
        pwa.pop(code, None)
        server.pop(code, None)

    only_server = sorted(set(server) - set(pwa))
    only_pwa = sorted(set(pwa) - set(server))
    differs = sorted(f"{c}: 服务端→{server[c]} ／ 界面→{pwa[c]}"
                     for c in set(server) & set(pwa) if server[c] != pwa[c])
    assert not (only_server or only_pwa or differs), (
        "**两张失败码别名表漂开了**——同一个码会给用户两句不同的话：\n"
        + (f"  只在服务端：{only_server}\n" if only_server else "")
        + (f"  只在界面：{only_pwa}\n" if only_pwa else "")
        + ("  指向不同：\n    " + "\n    ".join(differs) if differs else "")
        + "\n确实要只在一侧的话，写进 ONE_SIDED_ON_PURPOSE 并说明为什么。"
    )
