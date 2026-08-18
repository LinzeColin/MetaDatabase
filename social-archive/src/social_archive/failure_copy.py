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
    # v0.0.0.22：**没授权 ≠ 没登录**，下一步在两个不同的地方。
    # 没登录 → 回平台页登录；没授权 → 回插件点「连接账号」，在浏览器弹的框里选允许。
    FailureCopy("BROWSER_SCAN_FAILED",
                "在你的浏览器里读 <平台> 的页面时没能完成。请打开该平台的收藏页、确认已登录，然后点 [ 重试 ]。",
                "重试", "needs_user_action"),
    FailureCopy("PLATFORM_PERMISSION_MISSING",
                "还没有获得读取 <平台> 页面的授权。请点 [ 连接账号 ]，"
                "在浏览器弹出的框里选「允许」。",
                "连接账号", "needs_user_action"),
    # v0.0.0.22（2026-08-07）：这一条原来落进 PRODUCT_FAULT_CODES，于是对他说
    # 「**这次没有取到内容**，问题在我们这边，已经记下来了。不用反复重试。」
    # **两处都不对**：
    #   · 内容取到了——正文、标题、链接全在库里，少的只是那个视频文件。
    #     他生产库里 33 条就是这样，而它们的正文一条不缺。
    #   · 「问题在我们这边、已经记下来了」听起来像会修。而它是**有意的边界**：
    #     抖音返回的东西 yt-dlp 解不了、B站回 412 风控，我们不绕（L0 边界），
    #     国内平台的 Cookie 按 INV-DOMESTIC-COOKIE-STAYS 一步都不离开浏览器。
    #     **这一条不会变**，说得像会变就是骗他等。
    FailureCopy("MEDIA_BLOCKED_BY_PLATFORM",
                "内容已经存下来了，只有视频/图片文件没取到——<平台> 把下载挡住了。"
                "我们不绕过平台的风控，所以这一条会一直是这样；正文和链接不受影响。",
                None, "informational"),
    FailureCopy("MEDIA_TYPE_UNSUPPORTED",
                "内容已经存下来了，只有那个文件没取到——它的格式我们还处理不了。"
                "正文和链接不受影响。",
                None, "informational"),
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
    # **没授权和没登录不是一回事**，而这一条尤其不能混。
    #
    # v0.0.0.22：这些平台的主机权限全在 optional_host_permissions 里，
    # 连接账号那一步才申请。**没有权限时 chrome.tabs.get() 连 url 都读不到**，
    # 于是代码原来算出空域名、回一句「读不出当前页面的域名」——
    # 那把人指向「是不是页面没打开」，而真因是授权没给或被撤销了。
    # 由「加载他真正下载的那个 zip」那个演练测出来（此前十个演练都在加载前
    # 把可选权限提成必给权限，这个状态从没被走过）。
    #
    # 落到 NOT_LOGGED_IN 会把他送回平台页去登录，那是错的方向；
    # 正确的下一步是回插件点一次「连接账号」。所以单独给一条。
    # （它在冻结词典里有自己的一条，不需要别名——留这行注释是为了说明
    #   为什么它不像 PLATFORM_PERMISSION_DENIED 那样被折叠到 NOT_LOGGED_IN）
    "OBSERVER_INSTALL_FAILED": "SERVER_UNREACHABLE",
    # ── B 站收藏夹取数（v0.0.0.7 / G1）。分三类，判据是**用户下一步该做什么**。
    #
    # 第一类：他自己做得了。落到词典里已有的那两句。
    "BILIBILI_NOT_LOGGED_IN": "NOT_LOGGED_IN",
    # -403：B 站说权限不够。最常见的成因就是登录态没带上或已过期，
    # 而 NOT_LOGGED_IN 那句正好把他引回 B 站页面去确认——下一步是对的。
    "BILIBILI_FORBIDDEN": "NOT_LOGGED_IN",
    # 一个收藏夹都没列出来。**这句不能说成「你没有收藏」**：
    # 接口在没带上登录态时同样回「成功 + 空」（实测 code:0 / data:null），
    # 两者在字节上分不开，而其中一个他自己就能解决。
    "BILIBILI_NO_FOLDERS": "NOT_LOGGED_IN",
    # 同步途中那个标签页没了或被导航走了 —— 和"标签页被关掉"是同一件事。
    "BILIBILI_TAB_UNAVAILABLE": "TAB_CLOSED",
    "BILIBILI_TAB_NOT_ON_PLATFORM": "TAB_CLOSED",
    # 第二类：真的是一次暂时性的网络失败，**重试确实可能好**。
    # 这里用 SERVER_UNREACHABLE 不违反上面那条禁令 —— 那条禁的是把
    # 「本版本没实现」说成「暂时连不上，重试」；这两个码是货真价实的连不上。
    "BILIBILI_NETWORK_ERROR": "SERVER_UNREACHABLE",
    "BILIBILI_HTTP_ERROR": "SERVER_UNREACHABLE",
    # **INTERCEPT_PREFIX_UNKNOWN 从这里搬走了**（2026-08-06）。
    # 它原先也别名成 SERVER_UNREACHABLE，就写在上面那段说明的第四行下面——
    # 而那段说明讲的正是「别把『本版本没实现』说成『暂时连不上服务器 [重试]』」。
    # 同一个坑，隔着四行又踩了一次。
    #
    # 它的真实含义（background.js 里那句原话）是：
    #     「还没有确认 <平台> 的收藏接口地址，这个平台暂时不能同步。」
    # 重试一万次也一样——要它变绿得先有人按诊断、把前缀固化下来（T09/T10）。
    # 已移入 DELIBERATELY_UNALIASED。
    "UPLOAD_FAILED": "SERVER_UNREACHABLE",
    # **BROWSER_SCAN_FAILED 从别名表里拿掉了**（v0.0.0.22）。
    # 它别名成 SERVER_UNREACHABLE，于是界面说「暂时连不上服务器」——
    # 而服务器好好的，出问题的是**在他浏览器里读平台页面**那一步。
    # 他会去查网络、查服务器，查一个没坏的东西。
    # 2026-08-07 在生产库里量到这个码出现过 5 次。现在它在冻结词典里有自己一条。
    "RELATION_URL_UNAVAILABLE": "SERVER_UNREACHABLE",
    # 原始媒体文件没取到（v0.0.0.7）。**这三个和「同步失败」不是一回事**：
    # 内容本身已经保存好了（标题、链接、正文都在），少的只是那个视频/图片文件。
    #
    # MEDIA_BLOCKED_BY_PLATFORM 是结构性的：抖音返回的东西 yt-dlp 解不了、
    # B站回 HTTP 412 风控。我们**不绕**（L0 边界），而国内平台的 Cookie
    # 按 INV-DOMESTIC-COOKIE-STAYS 一步都不离开浏览器——服务端拿不到就是拿不到。
    # 所以它落 PRODUCT_FAULT_CODES：结论是「问题在我们这边，别反复重试」。
    # MEDIA_TEMPORARILY_UNAVAILABLE 才是真的可以再试（限流、超时）。
    "MEDIA_TEMPORARILY_UNAVAILABLE": "RATE_LIMITED",
    # 诊断按钮读回来那一段（v0.0.0.7 / T08）。**这三个都不别名成 NOT_LOGGED_IN**：
    # 它们说的是「我们读不懂平台给的东西」，让用户去重新登录只会让他白忙一趟。
    # 落到 PRODUCT_FAULT_CODES：结论是「问题在我们这边，别反复重试」。
    #
    # 唯独 B 站那条 `code:0 / data:null` **确实**别名成 NOT_LOGGED_IN——
    # 因为它的真实含义就是「这个浏览器没登录」（2026-08-04 实测，见
    # platform_payloads.py 模块文档）。解析器直接给出 NOT_LOGGED_IN，
    # 不经过这张表。
    #
    # NOTHING_CAPTURED 例外：观察器一条都没拦到，用户滚几屏再点一次就可能好，
    # 所以它是 retryable 而不是产品缺陷。
    "NOTHING_CAPTURED": "RATE_LIMITED",
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
    # 服务端读不出 B 站 uid（账号行里那个字段不是空间地址也不是数字）。
    # 对用户就是「这个账号得重连一次」——重连时会把空间地址写回去。
    "BILIBILI_UID_UNKNOWN": "CREDENTIAL_EXPIRED",
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
    # 同一类：**这个平台的收藏接口地址还没被确认过**，所以取数路装不起来。
    # 和上面那条的区别只是「哪一段没装」，对用户是同一件事：重试没有用。
    #
    # 今天它还打不到用户面前（只有诊断那条路会装观察器，而诊断分支
    # 自己推前缀、不查表）。**但 T10 一接上非诊断安装路，它立刻就可达**——
    # 那时候如果还别名着「暂时连不上服务器」，就又是一次让人无穷重试。
    "INTERCEPT_PREFIX_UNKNOWN",
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
    # ── B 站收藏夹（v0.0.0.7 / G1）第三类：**读到了一部分，但没读完。**
    # 这几个码的共同点是「已取到的都在库里，只是这次没到底」，
    # 正是 _INCOMPLETE_SENTENCE 那句话说的情形。
    #
    # 把它们放进这里而不是 PRODUCT_FAULT_CODES 是有后果的：产品故障那句
    # 说「不用反复重试」，而这几种**再跑一次通常就补齐了**。
    "BILIBILI_TOO_MANY_PAGES",             # 收藏夹超过翻页上限，只读了前面一段
    "BILIBILI_PAGINATION_STUCK",           # 接口说还有更多、却给了空页，停在这里
    "BILIBILI_COUNT_MISMATCH",             # 声明 N 条、只读到 M 条，差额没有解释
    "BILIBILI_SOME_FOLDERS_INCOMPLETE",    # 有收藏夹没读完
    "BILIBILI_SOME_ITEMS_HAVE_NO_URL",     # 有条目读不出可打开的网址，已跳过并记下
    # 按形状认列表那条路（v0.0.0.21 / 小红书·抖音·快手）：
    # **一次只看得到他滚动过的那些**。页面加载时先发一批，往下滚才发下一批。
    # 这不是失败，是没读完——已取到的都在库里，再同步一次能读到更多。
    # **绝不能报 complete**：报了会让"消失检测"把没滚到的当成他取消了收藏。
    "PARTIAL_BY_PAGE_SCROLL",
})
_INCOMPLETE_SENTENCE = "这次同步卡住了，没有正常结束。你已经取到的内容都还在。"

# **「没读完」和「卡住了」不是一回事**，而按形状读那条路每一次成功都报"没读完"。
#
# 2026-08-07 量到的：
#   第一次（读到 7 条新的）  →「新增 7 条。」            对
#   之后每 6 小时（没有新增）→「这次同步卡住了，没有正常结束。」+ 一颗「重试」
#
# 后面那种是**稳态**：页面加载时发出的那一批他已经存过了，再同步自然没有新增。
# 于是他每 6 小时看到一次"卡住了"，点重试还是同一批——
# **一个永远变不绿的红不是信号，是噪音**，而这个仓为这句话立过判据。
_SCROLL_PARTIAL_SENTENCE = (
    "这次没有读到新的内容——页面加载时能看到的那一批，都已经在你的档案馆里了。"
    "想要更早的：打开收藏页往下滚动一会儿，再点一次同步。"
)
SCROLL_PARTIAL_CODES: frozenset[str] = frozenset({"PARTIAL_BY_PAGE_SCROLL"})

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
    # 同一类，只是「哪一段没装」不同：**这个平台的收藏接口地址还没被确认过**，
    # 所以观察器装不起来（background.js 里那句原话是「还没有确认 <平台> 的
    # 收藏接口地址，这个平台暂时不能同步」）。
    #
    # 它原先别名成 SERVER_UNREACHABLE，就写在那段「别把『没实现』说成
    # 『暂时连不上服务器 [重试]』」的说明下面第四行——**同一个坑隔着四行又踩一次**。
    # 今天它还打不到用户面前（只有诊断那条路装观察器，而诊断自己推前缀、不查表），
    # **但 T10 一接上非诊断安装路它立刻可达**。
    "INTERCEPT_PREFIX_UNKNOWN",
    # 连接器视图被钳到能力声明之下时用的码（v0.0.0.7 / registry.health_views）。
    # 结论与 ACQUISITION_PATH_NOT_INSTALLED 同一类：**这条路本版本就没装**，
    # 不是用户做错了什么，也不是重试能解决的。真正要显示的那句中文
    # 由 NOT_SYNCABLE_YET 逐平台给出（「现在可以：…」那半句在那里）。
    "PLATFORM_NOT_SYNCABLE_YET",
    # 拦到了平台的响应，却读不懂它（v0.0.0.7 / T08）。
    # 让用户重试没有意义——同一份字节我们还是读不懂；要改的是解析器。
    "UNREADABLE",
    "PAYLOAD_NOT_JSON",
    "PAYLOAD_SHAPE_CHANGED",
    "PLATFORM_PARSER_MISSING",
    "PLATFORM_REFUSED",
    "MEDIA_BLOCKED_BY_PLATFORM",
    "MEDIA_NOT_RETRIEVED",
    "MEDIA_TYPE_UNSUPPORTED",
    # ── B 站收藏夹（v0.0.0.7 / G1）第四类：**知道原因，但他帮不上忙。**
    # B 站回了我们没处理过的错误码，或者回了我们读不懂的形状——
    # 两种都得我们改解析器，重试一万次是同一份字节。
    "BILIBILI_API_ERROR",
    "BILIBILI_SHAPE_UNKNOWN",
    # 「成功码 + 空数据」。登录态那条路已经由上面 BILIBILI_NOT_LOGGED_IN /
    # BILIBILI_NO_FOLDERS 单独接住了；能走到这一个，说明账号是认得的、
    # 收藏夹清单也拿到了，偏偏某个收藏夹回了 data:null —— 那就是我们的事。
    "BILIBILI_FOLDER_NOT_VISIBLE",
    # 服务端直接读公开收藏夹那条路（2026-08-17）。B 站接口连不上/限流 ——
    # 是传输问题，下一轮会自己重来，不用他做什么。
    "BILIBILI_API_FAILED",
    "BILIBILI_NO_RESULT",       # 注入的读取器什么都没返回
    "BILIBILI_READ_FAILED",     # 兜底：读取器报了失败但没给码
    # 在页面发出的响应里没认出收藏列表（v0.0.0.21 / 形状识别）。
    # **这一条更可能是"他不在收藏页上"而不是产品坏了**，但重试同一页没用——
    # 要他换到收藏页并往下滚。文案里那句话已经这么说了，
    # 所以归到「我们这边的事」而不是给一颗重试按钮。
    "LIST_SHAPE_NOT_RECOGNISED",
})
_PRODUCT_FAULT_SENTENCE = "这次没有取到内容，问题在我们这边，已经记下来了。不用反复重试。"

# 备份那条链停了时给他看的话。**放在这本词典里，不放在 api.py**——
# 这个仓的规矩是「词典只有一处真源」，而 2026-08-13 我第一版把它写在了
# `api.py` 的函数里：`check_docs_match_the_ui.py` 的语料只有 `apps/` 下的
# .js/.html，于是**说明书引用这句话时被判成「界面上找不到」**——
# 判据没错，是那句话没待在它该待的地方。
BACKUP_STALE_TAIL = "——已存下的内容一条都没少，停下来的是「再存一份到别处」这件事。"


def backup_stale_sentence(hours: float | None) -> str:
    """备份很久没跑过了。`hours` 是距上次跑完的小时数。"""
    if hours is not None and hours >= 1:
        return f"备份已经 {int(hours)} 小时没有跑过了{BACKUP_STALE_TAIL}"
    return f"备份已经有一会儿没有跑过了{BACKUP_STALE_TAIL}"


BACKUP_RUN_INCOMPLETE_SENTENCE = (
    "最近一次备份没跑完——已存下的内容一条都没少，但这一轮的副本没有做上去。")


# 上面那几句说的都是**「再存一份到别处」那条链**（replication）。
# 下面这两句说的是另一条：**连第一份新备份都没做出来**（backup）。
#
# 两条链是分开的定时器，可以只死一条——2026-08-12~13 生产上就是这样：
#
#     20260811T032747Z   ← 最后一次自动备份
#     （8/12、8/13 两天的定时备份整个缺失，200/CHDIR 各失败一次）
#     20260813T085049Z   ← 人手触发才补上的
#
# 而同期 replication 一直跑得好好的，于是活性那一格是绿的、界面一个字都没有。
# **上一轮我只把 replication 接了出来，就以为这条线补完了。**
NO_BACKUP_YET_SENTENCE = "还没有做出过任何一次备份。"


def backup_missing_sentence(hours: float | None) -> str:
    """连着很久没有做出新的备份。`hours` 是距最近一次做完的小时数。

    措辞和 replication 那句同一个规矩：先按住他最担心的事（旧的没少），
    再说清真正丢的是什么（这段时间新进来的东西还没进过备份）。"""
    if hours is not None and hours >= 1:
        return (f"已经 {int(hours)} 小时没有做出新的备份了"
                "——之前存下的内容一条都没少，"
                "但这段时间里新进来的东西还没有进过备份。")
    return ("最近一次备份没有做完——之前存下的内容一条都没少，"
            "但这一轮没有做出新的备份。")


# ## 第三轮：同一个病根，压着的是 replication 的**「从来没跑过」**那一支
#
# 上面那段注释写着「上一轮我只把 replication 接了出来，就以为这条线补完了」。
# 2026-08-14 反过来又犯一次：**我把 backup 的「从来没跑过」接了出来，
# 而 replication 的同名状态一个字都不说。**
#
# 拿空数据根起真 app 量出来的（不是读代码推的）：
#
#     backup       从没跑过 → message_zh="还没有做出过任何一次备份。"  徽标会说话
#     replication  从没跑过 → **连 message_zh 这个键都没有**            徽标全哑
#
# 哑的原因是那一支 `except (OSError, ValueError)` 把三件事收成了一个：
# 文件不在（**知道**：脚本跑一次就会写它，没有就是没跑过）、
# 读不动（**不知道**：权限之类，不该拿它吓人）、
# 不是合法 JSON（**知道**：状态坏了）。收成一个之后只能统一答"unknown"，
# 而 unknown 按设计是不说话的——于是"确实没跑过"搭了"不知道"的便车溜过去。
#
# 这正是 2026-08-04 那次事故的形状：三个 timer 全 disabled、90 天 No entries，
# 而界面照样显示「已归档」。
NO_REPLICATION_YET_SENTENCE = (
    "还没有把任何一份内容复制到别处——你存下的东西都在，"
    "但目前它们只存在这一台机器上。")


REPLICATION_STATUS_UNREADABLE_SENTENCE = (
    "复制这一步的状态记录坏掉了——你存下的东西都在，"
    "但现在没办法确认它们到底有没有第二份。")


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



# 「导进了东西，但这次没到底」时补在「新增 N 条。」后面的那半句。
# 单独拎出来是为了让判据钉得住它，也免得两处各写一遍。
_IMPORTED_INCOMPLETE_TAIL = "这次没跑完，可能还有没取到的——再同步一次试试。"
# **别写「接着找」**（2026-08-12 查证）：`last_sync_at` 只在同步
# **完整跑完**时才写，而他从没完整跑完过，所以再点一次跑的是 `first_full`——
# 从头重扫，不是从断点续。反过来，一个曾经跑完过的账号又出现 INCOMPLETE 时
# 走的是 `incremental`，「重新找一遍」在那种情况下又是错的。
# 两种模式下都成立的话只有「再同步一次试试」，所以就说这句。


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
        #
        # **但「没跑完」不能被这句话吞掉**（2026-08-12，生产实测）。
        #
        # 他那 20 次同步里真的导进东西的只有 4 次，而这 4 次**全部**是
        # 「导进了东西 + 属于 INCOMPLETE_RUN_CODES」：
        #
        #     bilibili 102/102 partial RELATION_SCOPE_UNCONFIRMED
        #     douyin    35/35  partial STABLE_END_WITHOUT_PROOF
        #     bilibili  67/67  partial RELATION_SCOPE_UNCONFIRMED
        #     douyin    56/56  partial STABLE_END_WITHOUT_PROOF
        #
        # 因为这个分支排在最前面，下面那条 INCOMPLETE 分支
        # （「这次同步卡住了，没有正常结束」）**在 imported > 0 时永远到不了**,
        # 而他的情况恰恰全是 imported > 0。于是四次都只说了「新增 N 条。」。
        #
        # `discovered == imported` 说明它把**找到的**都拿回来了，却证不出
        # 「确实到头了」——也就是可能还有没被发现的。他看到「新增 102 条」
        # 会合理地以为同步完成了；而从 8-04 起再没进过一条。
        #
        # 「中途出过可恢复的错」和「没到底」不是一回事，只给后者补话。
        # **减掉 SCROLL_PARTIAL_CODES**（2026-08-12，是判据拦下来的）。
        #
        # `PARTIAL_BY_PAGE_SCROLL` 两个集合里都有。对它，「没跑完」是真的，
        # 而「再同步一次试试」是**假的出路**：不往下滚，再点一次读到的还是同一批。
        # 已有判据 test_a_scroll_partial_with_nothing_new_is_not_shown_as_stuck
        # 把这件事写得很清楚：「给了一颗『重试』——点了读到的还是同一批，
        # 那是一颗骗人的按钮」。它拦住了我，拦得对。
        # 那一类自己那句「往下滚一会儿再同步」才是能用的，别被这里盖掉。
        incomplete = (code_key(failure_code) in INCOMPLETE_RUN_CODES
                      and code_key(failure_code) not in SCROLL_PARTIAL_CODES)
        return {
            "outcome": "imported_incomplete" if incomplete else "imported",
            "imported": imported,
            "message_zh": (f"新增 {imported} 条。{_IMPORTED_INCOMPLETE_TAIL}"
                           if incomplete else f"新增 {imported} 条。"),
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
    if str(code_key(failure_code)) in SCROLL_PARTIAL_CODES:
        # **这不是失败，也不是卡住**：他能看到的那一批已经全在库里了。
        # 给的是"想要更多该怎么做"，不是一颗点了也一样的「重试」。
        return {
            "outcome": "informational", "imported": imported,
            "message_zh": _SCROLL_PARTIAL_SENTENCE,
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
    if str(status).lower() in {"cancelled", "canceled"}:
        # **被中断不是失败，更不是产品坏了。**
        #
        # 2026-08-07 拿 Owner 生产库里那 20 次同步逐条渲染，发现有一条
        # `cancelled`（没有 failure_code、0 条）落到了最下面那句
        # 「我们没能记录下原因。**这是产品的问题**」——而 cancelled 的来路是
        # db.py 断开账号时那一步：「把还在跑的 sync_run 落到 cancelled
        # （否则界面上永远转圈）」。**那是有人主动断开，不是产品出错。**
        #
        # 这和上面那条「刚排上队就被告知产品坏了」是同一种错，换了个状态：
        # 把一个正常的状态扣上"产品有问题"的帽子。
        return {
            "outcome": "cancelled", "imported": imported,
            "message_zh": "这次同步被中断了（多半是那时断开了账号）。"
                          "已经取到的内容都还在，重新连接之后可以再同步一次。",
            "failure_code": None, "action_zh": None,
        }
    # 到这里说明：0 条、没有失败码、也没跑完。这正是 v0.0.0.6 的那种静默的零。
    return {
        "outcome": "unexplained_zero", "imported": 0,
        "message_zh": "这次没有取到任何内容，而且我们没能记录下原因。这是产品的问题，请重试一次；如果还是这样，请联系我们。",
        "failure_code": "UNEXPLAINED_ZERO", "action_zh": "重试",
    }


# ## worker 和接口跑在不同版本上（2026-08-14）
#
# 部署被打断时可能 api 换了新镜像而 core-worker 还跑旧的。
# 那时四个信号全正常：`version` 是 api 报的（新的）、`worker.alive` 是 true
# （旧 worker 照样发心跳）、两条备份链也没事——**而后台跑的是旧代码**。
#
# 2026-08-06 出过它的一个变体：SIGTERM 打断在 `docker compose up` 中间，
# core-worker 卡在 Created、后台任务全积压，而 /health 是好的。
# 那一种后来被 `worker.alive` 查出来了；**这一种（活着但是旧的）在此之前查不出来**。
def worker_version_mismatch_sentence(api_version: str, worker_version: str | None) -> str:
    """接口和后台跑在不同版本上。`worker_version` 为 None = 旧 worker 根本不写版本。"""
    if not worker_version:
        return ("后台跑的是一个不报版本的旧版——你已经存下的东西一条都没少，"
                "但新收进来的可能是按旧规则处理的。")
    return (f"接口是 {api_version}、后台是 {worker_version}，两边版本对不上"
            "——你已经存下的东西一条都没少，但新收进来的是按后台那一版处理的。")
