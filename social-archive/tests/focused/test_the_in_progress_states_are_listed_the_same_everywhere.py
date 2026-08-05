"""「同步还在跑」这七个状态，全仓抄了十四份，其中五份少一个（v0.0.0.7 / T13）。

## 为什么要钉它

`failure_copy.IN_PROGRESS_STATES` 的注释写着「与 background.js 的
`ACTIVE_SYNC_STATES` 对应」——**一句话点明了两处要对应，却没有任何东西在核**。

2026-08-06 数了一遍，不是两处，是**十四处**：

    src/social_archive/failure_copy.py      IN_PROGRESS_STATES
    src/social_archive/db.py           ×2   pause / cancel 的状态迁移表
    apps/browser-extension/background.js    ACTIVE_SYNC_STATES
    apps/browser-extension/options.js       内联字面量
    apps/browser-extension/sidepanel.js     内联字面量
    apps/browser-extension/popup.js    ×4   内联字面量
    apps/pwa/app.js                    ×4   内联字面量

数清楚一点（**第一版这里写「十一处是匿名的」，那是我自己数错了**——
用来分类的启发式把 Python 那两个具名常量也算成了匿名）：

    4 处是具名常量，而且**三个不同的名字**：
        IN_PROGRESS_STATES（服务端）、ACTIVE_SYNC_STATES（background）、
        activeStates（options）、running（sidepanel）
    2 处是 db.py 状态迁移表里 pause / cancel 两个键
    **8 处是彻头彻尾的匿名内联数组**

匿名那些最容易漂：加一个新状态的人只会改自己手边那一处。
而三个不同的名字意味着，就算想全局搜一遍也搜不齐。

**而它已经漂了。** 这条判据第一次跑就红在五处：popup.js 四处、app.js 一处，
**全都少了 `authorizing`**。后果是：账号正在授权那一段，
弹窗的活动计数是 0、不显示「同步 N/M」、也不去轮询刷新——
**明明在跑，界面说没在跑**。看着像是从一份还没有 authorizing 的旧清单抄下来的。
五处都补上了。

## 判据

全仓凡是列出这组状态的地方（认门槛：七个里出现 ≥5 个），
那一组必须**正好**等于三种登记过的变体之一：

    这七个                              —— 「在跑」
    这七个 + paused                     —— 「可取消／可断开」（暂停中的也该能取消）
    这七个 + failed + blocked_environment —— 「待处理计数」（跑着的 + 需要人管的）

**每一种都必须完整包含那七个**，差别只许在多出来的那几个上。

## 它不保证什么

- 只认**字面量写在一起**的那种。拆成常量再拼、或者从接口取的，看不见。
- 不保证这七个状态本身是对的，只保证**九处说的是同一件事**。
"""

from __future__ import annotations

import re
from pathlib import Path

from social_archive.failure_copy import IN_PROGRESS_STATES

ROOT = Path(__file__).resolve().parents[2]
STATES = frozenset(IN_PROGRESS_STATES)
# **三种有名有姓的变体，每种都写清是给谁用的。**
# 允许变体不等于放任：每一种都必须**完整包含那七个**，差别只在多出来的那几个。
VARIANTS: dict[frozenset[str], str] = {
    STATES: "在跑",
    STATES | {"paused"}: "可取消／可断开（暂停中的也该能取消）",
    STATES | {"failed", "blocked_environment"}: "待处理计数（跑着的 + 需要人管的）",
}
# 出现这么多个就算「这是在列同步进行中的状态」。低于它多半是别的意思。
LOOKS_LIKE_THE_LIST = 5


def _literal_groups() -> list[tuple[str, int, frozenset[str]]]:
    out: list[tuple[str, int, frozenset[str]]] = []
    for folder in ("src", "apps"):
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or path.suffix not in (".py", ".js"):
                continue
            if "__pycache__" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r"[\[\{\(][^\[\]\{\}\(\)]{20,500}[\]\}\)]", text, re.S):
                names = frozenset(re.findall(r'"(\w+)"', match.group(0)))
                if len(names & STATES) >= LOOKS_LIKE_THE_LIST:
                    line = text[: match.start()].count("\n") + 1
                    out.append((str(path.relative_to(ROOT)), line, names))
    return out


def test_every_copy_of_the_in_progress_list_says_the_same_thing() -> None:
    groups = _literal_groups()
    # **一处都没扫到，和「九处全一致」长得一样。**
    assert len(groups) >= 6, (
        f"只扫到 {len(groups)} 处在列这组状态——判据的射程失效了，先修判据"
    )
    wrong = [
        f"{path}:{line} → 少 {sorted(STATES - names) or '—'}"
        f"／多出且没登记 {sorted(names - STATES - {'paused', 'failed', 'blocked_environment'}) or '—'}"
        for path, line, names in groups
        if names not in VARIANTS
    ]
    assert not wrong, (
        "**「同步还在跑」这组状态在各处不一致**——漂开的后果是"
        "「明明在跑，界面说没在跑」：\n  " + "\n  ".join(wrong)
    )


def test_the_extension_and_the_server_still_agree() -> None:
    """两处具名的那一对单独钉住。

    `failure_copy.IN_PROGRESS_STATES` 的注释说它「与 background.js 的
    `ACTIVE_SYNC_STATES` 对应」——**把那句注释变成判据**。
    上面那条是通则，但它靠「≥5 个」这个门槛认路；万一有人把
    `ACTIVE_SYNC_STATES` 拆成两半写，通则就认不出来了，这条还认得。
    """
    background = (ROOT / "apps/browser-extension/background.js").read_text(encoding="utf-8")
    found = re.search(r"ACTIVE_SYNC_STATES\s*=\s*(?:new Set\()?\[([^\]]*)\]", background)
    assert found, "background.js 里的 ACTIVE_SYNC_STATES 不见了——判据要跟着改"
    assert frozenset(re.findall(r'"(\w+)"', found.group(1))) == STATES, (
        "扩展与服务端对「同步还在跑」的定义不一样了"
    )
