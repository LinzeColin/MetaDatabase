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
from datetime import UTC, datetime


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
    # T03 拆掉取数通道之后的显式失败。
    #
    # **这里原先别名成 SERVER_UNREACHABLE，那是错的。** 那句词典文案是
    # 「暂时连不上服务器。你的数据没有丢，[ 重试 ]」——而真实原因是
    # **本版本根本没有实现这条取数路**。于是界面让用户一遍遍重试一件
    # 永远不可能成功的事。Owner 的原话：「不知道应该怎么操作。」
    #
    # 正确的做法有两层，缺一不可：
    #   · 界面**根本不给这些平台画「立即同步」按钮**（account_sync.SYNCABLE_NOW），
    #     从源头上不让用户点到——这是主要修法。
    #   · 万一还是走到这个码，落进 DELIBERATELY_UNALIASED：文案说
    #     「这是产品的问题，请联系我们」，把人导向对的地方，
    #     而不是导向一个无穷重试。
    "LOGIN_PROOF_UNAVAILABLE": "NOT_LOGGED_IN",
    # 扩展侧
    "PERMISSION_DENIED": "NOT_LOGGED_IN",
    # 没授权读平台页面：对用户来说下一步是"去授权"，和"去登录"不是一回事，
    # 但词典里没有单独一句，暂时落到最接近的那条（NOT_LOGGED_IN 会引导他回到平台页）。
    "PLATFORM_PERMISSION_DENIED": "NOT_LOGGED_IN",
    "OBSERVER_INSTALL_FAILED": "SERVER_UNREACHABLE",
    "INTERCEPT_PREFIX_UNKNOWN": "SERVER_UNREACHABLE",
    "UPLOAD_FAILED": "SERVER_UNREACHABLE",
    "BROWSER_SCAN_FAILED": "SERVER_UNREACHABLE",
    "RELATION_URL_UNAVAILABLE": "SERVER_UNREACHABLE",
    # 标签页/会话
    "MIRROR_TAB_CLOSED": "TAB_CLOSED",
    "PLATFORM_SESSION_EXPIRED": "CREDENTIAL_EXPIRED",
    # gallery-dl 退出码 8（ChallengeError）：撞上验证码/设备风控。
    # 我们**不绕**（L0 边界），只能把人引回浏览器自己过一次。
    # 冻结词典里没有「验证码」这一条，落到最接近的 NOT_LOGGED_IN——
    # 它的下一步动作（回浏览器操作后重试）是对的，只是措辞说的是"登录"。
    # 这是词典的缺口，不是映射的将就，见 evidence/T12/EXIT_CODE_CONTRACT.json。
    "CHALLENGE_REQUIRED": "NOT_LOGGED_IN",
    # ── 连接器层（connectors/command.py）──
    # 这一层的码此前**整层都没进过词典**：七个码全部落到「我们没能记录下原因」，
    # 而原因就写在异常里。教训与生产遗留码那次相同，但这次不是数据的问题——
    # **是我只扫了同步路径，没扫连接器路径。**
    "CLI_WORKER_FAILED": "SERVER_UNREACHABLE",        # sidecar 连不上/报错，重试有意义
    "CLI_WORKER_COMMAND_FAILED": "SERVER_UNREACHABLE",
    "COMMAND_FAILED": "SERVER_UNREACHABLE",
    "COMMAND_TIMEOUT": "SERVER_UNREACHABLE",          # 超时，重试有意义
    "BILI_COMMAND_FAILED": "SERVER_UNREACHABLE",
    "BILI_RATE_LIMITED": "RATE_LIMITED",              # 词典里本来就有这一条
    # 缺 Instagram 会话或缺 instaloader。对用户来说下一步是去连 Instagram。
    "INSTAGRAM_SESSION_OR_BINARY_MISSING": "NOT_LOGGED_IN",
    "INSTAGRAM_SIDECAR_BLOCKED": "SERVER_UNREACHABLE",
    # ── 账号 / OAuth / 各 worker ──
    # 这一批是 scripts/check_every_failure_code_is_explainable.py 扫出来的：
    # 一次性找到 24 个说不出人话的码。此前词典只覆盖了同步路径的一小部分。
    "ACCOUNT_REAUTH_REQUIRED": "CREDENTIAL_EXPIRED",
    "REDDIT_AUTH_MISSING": "REDDIT_NOT_AUTHORIZED",
    "REDDIT_RATE_LIMITED": "RATE_LIMITED",
    "INSTAGRAM_SESSION_PERMISSIONS": "NOT_LOGGED_IN",   # 会话文件权限不安全，我们拒用；要重新上传
    "X_API_FAILED": "SERVER_UNREACHABLE",
    "REDDIT_API_FAILED": "SERVER_UNREACHABLE",
    "XHS_WORKER_FAILED": "SERVER_UNREACHABLE",
    "WORKER_PROBE_OR_CALL_FAILED": "SERVER_UNREACHABLE",
    "INSTALOADER_FAILED": "SERVER_UNREACHABLE",
    "BILI_INVALID_RESPONSE": "SERVER_UNREACHABLE",
    "OBSIDIAN_LOCAL_BRIDGE_FAILED": "SERVER_UNREACHABLE",
    "X_AUTH_MISSING": "CREDENTIAL_EXPIRED",   # X 没授权过或授权掉了 → 去重新连接
    "X_RATE_LIMITED": "RATE_LIMITED",
    # 三处「没归类的异常」兜底码。它们原来直接用 Python 类名当码
    # （CONNECTORERROR / HEALTH_XXXERROR / …），那是个无限集合，
    # 词典永远追不上，于是界面只能说「我们没能记录下原因」。
    # 生产 connector_state 里就躺着一个 CONNECTORERROR。
    "DESTINATION_PROBE_FAILED": "SERVER_UNREACHABLE",
    "HEALTH_PROBE_FAILED": "SERVER_UNREACHABLE",
    "JOB_FAILED": "SERVER_UNREACHABLE",
    # 生产历史数据里已经存在的那个类名码，也认一下——库里的记录改不了
    "CONNECTORERROR": "SERVER_UNREACHABLE",
    "ITEM_INGEST_FAILED": "SERVER_UNREACHABLE",
    "BILI_SIDECAR_BLOCKED": "SERVER_UNREACHABLE",
}

# **故意不放进 _ALIASES 的码**，写在这里是为了让"没漏，是有意的"这件事看得见：
#
#   URL_NOT_SUPPORTED —— gallery-dl 退出码 32/64。意思是我们把一个它不认识的
#   URL 传了进去，这是**我们的 bug，不是用户的**。
#   映射到 SERVER_UNREACHABLE（"暂时连不上服务器…[重试]"）会让用户一直重试，
#   而重试一万次也一样——正是 gallerydl_runner 模块文档里明令禁止的那种误判。
#   不给别名，它就会落到下面的 unexplained_zero：
#   "这是产品的问题，请重试一次；如果还是这样，请联系我们。"
#   ——结论对（是我们的问题、去找我们），代价是那句"我们没能记录下原因"
#   在这里不准确（原因是记了的，就在 last_error_code 里）。
#   要真正说准，得往冻结词典里加一条，那是改产品合同，先改 ZERO_BARRIER_UX.md。
#   —— 现在它由 PRODUCT_FAULT_CODES 接管：结论仍是「我们的问题、别重试」，
#   但不再借用那句不准确的「我们没能记录下原因」。
DELIBERATELY_UNALIASED: frozenset[str] = frozenset({
    "URL_NOT_SUPPORTED",
    # 本版本没有实现这条取数路。给它任何别名都会变成一句「重试」，
    # 而重试一万次也一样。落进 unexplained_zero 的「这是产品的问题、
    # 请联系我们」虽然措辞也不完美，但**它把人导向对的方向**。
    # 主要修法在界面侧：这些平台根本不画「立即同步」按钮。
    "ACQUISITION_PATH_NOT_INSTALLED",
})

# 「没有新增」不是失败。它必须与失败**显示成两种东西**。
NOTHING_NEW = FailureCopy(
    "NOTHING_NEW", "已经是最新的，没有新增内容。", None, "informational"
)

# 还在跑的状态。这些**不是终态**，所以既不能报成功，也不能报失败。
# 与 background.js 的 ACTIVE_SYNC_STATES 对应。
IN_PROGRESS_STATES: frozenset[str] = frozenset({
    "queued", "authorizing", "discovering", "scanning",
    "normalizing", "artifacting", "exporting",
})

# 「没跑完」类的失败码。共用一句话，因为对用户来说它们是同一件事：
# 这次没走完，已经拿到的东西还在，可以再来一次。
#
# **这份名单不是靠读代码列出来的，是查生产库查出来的。**
# 2026-08-04 在生产 sync_run 表里实际存在的失败码只有四种：
#
#     BROWSER_SCAN_FAILED         4 次   ← 早就在别名表里
#     RELATION_SCOPE_UNCONFIRMED  7 次（已入库 169 条）
#     STABLE_END_WITHOUT_PROOF    2 次（已入库  91 条）
#     SYNC_RUN_ABANDONED          3 次
#
# 后三个**在当前代码里一个字都搜不到**——它们是 v0.0.0.6 留下的，
# 那部分代码已经被 T03 删掉了，但记录还躺在库里。
# 不认它们的后果：这 12 条历史记录在界面上会显示成
# 「我们没能记录下原因」，而原因白纸黑字写在 last_error_code 里。
#
# 教训：失败文案词典是照着我能读到的代码路径建的，而生产库里有
# 代码里已经不存在的码。**光读代码列不全，得去查真实数据。**
INCOMPLETE_RUN_CODES: frozenset[str] = frozenset({
    "SYNC_STALLED",               # 本版新增：非终态但很久没动
    "SYNC_INTERRUPTED",           # 本版新增：worker 反复被杀，放弃
    "SYNC_RUN_ABANDONED",         # v0.0.0.6 遗留
    "RELATION_SCOPE_UNCONFIRMED", # v0.0.0.6 遗留
    "STABLE_END_WITHOUT_PROOF",   # v0.0.0.6 遗留
    # 到了单次同步的条数上限就停——**不是失败**，是没跑完。
    # 已取到的都在库里，下次续着跑。用「卡住了…都还在」这句正合适。
    "ACCOUNT_SYNC_ITEM_LIMIT_REACHED",
    # 关系没拿到终批证明——扫完了但证不出"确实到头了"。
    # 对用户就是「没跑完，已取到的还在」，与其它 INCOMPLETE 同类。
    "RELATION_TERMINAL_NOT_PROVEN",
})
_INCOMPLETE_SENTENCE = "这次同步卡住了，没有正常结束。你已经取到的内容都还在。"

# **「是我们的问题」与「我们不知道为什么」是两回事。**
#
# 原来这两种都落到 unexplained_zero，那句话里有「我们没能记录下原因」——
# 对下面这些码是**假话**：原因记得清清楚楚（部署没配、URL 不支持、
# 命令不在白名单），只是用户帮不上忙。说「不知道原因」会让用户
# 反复重试一个永远不会好的东西，还顺带损失了我们本可以给出的诚实。
#
# 这些码的共同点：**用户做什么都没用，得我们去修。**
PRODUCT_FAULT_CODES: frozenset[str] = frozenset({
    "URL_NOT_SUPPORTED",            # gallery-dl 退出码 32/64：我们传错了 URL
    "CLI_WORKER_NOT_CONFIGURED",    # 部署里压根没配下载 sidecar
    "CLI_WORKER_INVALID_RESPONSE",  # sidecar 回了我们读不懂的东西
    "COMMAND_NOT_ALLOWED",          # 我们请求了一个不在白名单里的命令
    "TOOL_NOT_ALLOWED",             # 同上：我们点名了一个不支持的工具
    "ACCOUNT_WRITE_FORBIDDEN",      # 我们试图写一个只读账号路径
    "INVALID_CONFIGURATION",        # 目的地配置错了，用户改不了
    "OPENAPI_INVALID_DOCUMENT",     # 我们喂给 worker 的 OpenAPI 文档有问题
    "OPENAPI_ROUTE_AMBIGUOUS",      # 同上
    # L0 边界：X 的付费 API 未确认零成本，我们**主动不走**。
    # 这是产品的选择，不是用户的错，重试也不会变——所以既不给重试按钮，
    # 也不说「我们不知道为什么」。
    "X_ZERO_COST_NOT_CONFIRMED",
    # 本版本没实现这条取数路（T03 删掉 DOM 抓取器、T08 的替代品还没缝上）。
    # 用户做什么都没用，得我们去补。**主要修法在界面侧**：这些平台
    # 根本不画「立即同步」按钮（见 account_sync.SYNCABLE_NOW）；
    # 这里是万一还是走到了的兜底——结论是「我们的问题、别重试」，
    # 而不是此前那句借来的「暂时连不上服务器，[ 重试 ]」。
    "ACQUISITION_PATH_NOT_INSTALLED",
})
_PRODUCT_FAULT_SENTENCE = "这次没有取到内容，问题在我们这边，已经记下来了。不用反复重试。"


def code_key(code: str | None) -> str:
    """失败码规范化。库里存的大小写不一定一致。"""
    return str(code or "").strip().upper()


def resolve(code: str | None) -> FailureCopy | None:
    """把任意失败码解析成词典里的一条。认不出来返回 None。"""
    key = str(code or "").strip().upper()
    if not key:
        return None
    if key in COPY_BY_CODE:
        return COPY_BY_CODE[key]
    aliased = _ALIASES.get(key)
    return COPY_BY_CODE.get(aliased) if aliased else None


def _is_stalled(updated_at: str | None, *, stale_after_seconds: int) -> bool:
    """非终态但很久没动过。判据是**多久没动**，不是当前是什么状态。

    时间戳缺失或读不懂时一律回 False —— 宁可少报，也不能把一堆正常运行
    误判成卡住（那会让"卡住"这个提示很快被用户学会忽略）。
    """
    stamp = str(updated_at or "").strip()
    if not stamp:
        return False
    try:
        moved = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return False
    if moved.tzinfo is None:
        moved = moved.replace(tzinfo=UTC)
    return (datetime.now(UTC) - moved).total_seconds() > stale_after_seconds


def describe_sync_outcome(
    *, imported: int, failure_code: str | None, platform_label: str = "", status: str = "",
    updated_at: str | None = None, stale_after_seconds: int = 1800,
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
    if code_key(failure_code) in PRODUCT_FAULT_CODES:
        # 知道原因、但用户帮不上忙。**不许说「我们不知道为什么」。**
        return {
            "outcome": "product_fault", "imported": imported,
            "message_zh": _PRODUCT_FAULT_SENTENCE,
            "failure_code": code_key(failure_code), "action_zh": None,
        }
    if str(code_key(failure_code)) in INCOMPLETE_RUN_CODES:
        # 「没跑完」——不是没原因，也不是成功。
        return {
            "outcome": "stalled", "imported": imported,
            "message_zh": _INCOMPLETE_SENTENCE,
            "failure_code": code_key(failure_code), "action_zh": "重试",
        }
    if str(status).lower() in IN_PROGRESS_STATES:
        if _is_stalled(updated_at, stale_after_seconds=stale_after_seconds):
            # 「正在同步，请稍候。」说一次是对的，说一整天就是骗人。
            # 这是 INV-NO-SILENT-ZERO 真正落到用户眼前的地方：界面读的是
            # /v1/sync-runs，而不是 /v1/status（那个端点根本没有客户端在读）。
            # 审计挂在 status 上只够运维查；要让用户看见，必须在这一句里说。
            return {
                "outcome": "stalled", "imported": imported,
                "message_zh": _INCOMPLETE_SENTENCE,
                "failure_code": "SYNC_STALLED", "action_zh": "重试",
            }
        # 还在跑，不是失败。
        # 修这一条之前，一次刚排上队的同步会显示
        # 「这次没有取到任何内容…这是产品的问题，请重试一次」——
        # 用户刚点完就被告知产品坏了，而它其实只是还没开始跑。
        #
        # 注意：这不是把「卡住不动」这件事藏起来。真正卡死的运行由
        # db.stalled_active_runs() 抓（那才是按"多久没动"判的），
        # 而不是靠给每一次正常的排队都扣一顶"产品有问题"的帽子。
        return {
            "outcome": "in_progress", "imported": imported,
            "message_zh": "正在同步，请稍候。", "failure_code": None, "action_zh": None,
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
