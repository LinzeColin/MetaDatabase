"""失败文案词典（v0.0.0.7 / T14）。

## 为什么需要它

INV-NO-SILENT-ZERO：**任何一次同步为 0 条时，界面都说得出为什么。**

v0.0.0.6 的失败长这样：同步跑完、界面显示成功、表格里 0 条、
没有任何地方说得出原因。用户唯一能做的是再点一次，然后再看一次 0。

这个模块把 `01_PRODUCT/ZERO_BARRIER_UX.md` 的「错误文案词典（冻结）」
变成代码。词典是**冻结**的：句子逐字照抄，包括标点和方括号按钮。
改这里的句子等于改产品合同，要先改那份文档。

## 两条硬规矩

  1. **「没有新增」与「失败」必须是两种不同的显示。**
     两者都是 0 条，但一个是好事（已经是最新的），一个是坏事（没跑通）。
     混成一句话，用户就永远分不清该不该重试。

  2. **界面上不得出现英文错误码或堆栈。**
     failure_code 是给日志和判据看的，给人看的永远是这里的中文句子。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureCopy:
    """一条失败文案。`action_zh` 是词典里方括号中的按钮。"""

    code: str
    template: str
    action_zh: str | None = None
    #  retryable：用户自己点一下就可能好。
    #  needs_user_action：要用户先去做点别的（登录、授权）。
    #  informational：不是失败，只是没有新增。
    kind: str = "retryable"

    def render(self, *, platform_label: str = "", count: int = 0) -> str:
        return self.template.replace("<平台>", platform_label or "该平台").replace("<N>", str(count))


# 逐字照抄 ZERO_BARRIER_UX.md 的冻结词典。左列是我们的 failure_code。
_DICTIONARY: tuple[FailureCopy, ...] = (
    FailureCopy("CREDENTIAL_EXPIRED", "<平台> 的登录状态过期了。[ 重新连接 ]",
                "重新连接", "needs_user_action"),
    FailureCopy("NOT_LOGGED_IN",
                "没有在浏览器里找到 <平台> 的登录状态。请先在浏览器里登录 <平台>，然后点 [ 重试 ]",
                "重试", "needs_user_action"),
    FailureCopy("REDDIT_NOT_AUTHORIZED", "Reddit 需要单独授权一次。[ 去授权 ]",
                "去授权", "needs_user_action"),
    FailureCopy("TAB_CLOSED", "<平台> 同步中断了，因为标签页被关掉。[ 继续 ]",
                "继续", "retryable"),
    FailureCopy("RATE_LIMITED",
                "<平台> 请求太频繁，已自动放慢。已经收到的 <N> 条都保住了，稍后会自动继续。",
                None, "informational"),
    FailureCopy("SERVER_UNREACHABLE", "暂时连不上服务器。你的数据没有丢，[ 重试 ]",
                "重试", "retryable"),
    FailureCopy("DISK_QUOTA",
                "存储空间快满了，已经暂停下载媒体文件，文字和链接还在正常保存。",
                None, "informational"),
)

COPY_BY_CODE: dict[str, FailureCopy] = {item.code: item for item in _DICTIONARY}

# 词典之外的内部码映射到词典里的某一条。
# 有这张表是因为代码里的失败码比词典细——但**界面上只许出现词典里的句子**。
_ALIASES: dict[str, str] = {
    # T03 拆掉取数通道之后的显式失败
    "ACQUISITION_PATH_NOT_INSTALLED": "SERVER_UNREACHABLE",
    "LOGIN_PROOF_UNAVAILABLE": "NOT_LOGGED_IN",
    # 扩展侧
    "PERMISSION_DENIED": "NOT_LOGGED_IN",
    "UPLOAD_FAILED": "SERVER_UNREACHABLE",
    "BROWSER_SCAN_FAILED": "SERVER_UNREACHABLE",
    "RELATION_URL_UNAVAILABLE": "SERVER_UNREACHABLE",
    # 标签页/会话
    "MIRROR_TAB_CLOSED": "TAB_CLOSED",
    "PLATFORM_SESSION_EXPIRED": "CREDENTIAL_EXPIRED",
}

# 「没有新增」不是失败。它必须与失败**显示成两种东西**。
NOTHING_NEW = FailureCopy(
    "NOTHING_NEW", "已经是最新的，没有新增内容。", None, "informational"
)


def resolve(code: str | None) -> FailureCopy | None:
    """把任意失败码解析成词典里的一条。认不出来返回 None。"""
    key = str(code or "").strip().upper()
    if not key:
        return None
    if key in COPY_BY_CODE:
        return COPY_BY_CODE[key]
    aliased = _ALIASES.get(key)
    return COPY_BY_CODE.get(aliased) if aliased else None


def describe_sync_outcome(
    *, imported: int, failure_code: str | None, platform_label: str = "", status: str = ""
) -> dict[str, object]:
    """一次同步跑完之后，界面该说什么。

    这是 INV-NO-SILENT-ZERO 的落点：**imported=0 且没有 failure_code 时，
    这里不会回一句含糊的话，而是回一条明确的 UNEXPLAINED_ZERO**。
    那条文案本身就在告诉用户「这是产品的问题，不是你的问题」，
    同时让这种情况在界面上无法伪装成成功。
    """
    resolved = resolve(failure_code)
    if imported > 0:
        # 有新增就是成功，即使中途有过可恢复的失败也先报数。
        return {
            "outcome": "imported", "imported": imported,
            "message_zh": f"新增 {imported} 条。",
            "failure_code": failure_code or None,
            "action_zh": resolved.action_zh if resolved else None,
        }
    if resolved is not None:
        return {
            "outcome": "failed" if resolved.kind != "informational" else "informational",
            "imported": 0,
            "message_zh": resolved.render(platform_label=platform_label, count=imported),
            "failure_code": resolved.code,
            "action_zh": resolved.action_zh,
        }
    if str(status).lower() in {"completed", "complete"} and not failure_code:
        # 真的跑完了、真的没有新增——这是好事，必须与失败区分开。
        return {
            "outcome": "nothing_new", "imported": 0,
            "message_zh": NOTHING_NEW.template, "failure_code": None, "action_zh": None,
        }
    # 到这里说明：0 条、没有失败码、也没跑完。这正是 v0.0.0.6 的那种静默的零。
    return {
        "outcome": "unexplained_zero", "imported": 0,
        "message_zh": "这次没有取到任何内容，而且我们没能记录下原因。这是产品的问题，请重试一次；如果还是这样，请联系我们。",
        "failure_code": "UNEXPLAINED_ZERO", "action_zh": "重试",
    }
