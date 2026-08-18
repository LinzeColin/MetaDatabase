from __future__ import annotations

import re
from pathlib import Path

import secrets
from dataclasses import dataclass
from typing import Any

from .config import Settings
from .db import RuntimeStore
from .models import AccountConnectRequest, AccountSyncRequest, CaptureRequest, ConnectorRunRequest, SyncBatchRequest
from .registry import ConnectorRegistry
from .service import ArchiveService
from .utils import utcnow


# 按形状读那条路认不出他是谁（它只读收藏页，不去主页），所以完成连接时
# 报这个固定值。它不是一个真的账号标识，**只是"这台浏览器里那个已登录的人"**。
UNIDENTIFIED_BROWSER_ACCOUNT = "browser-session"

PLATFORM_RELATIONS: dict[str, list[str]] = {
    "xiaohongshu": ["favorite", "like"],
    "douyin": ["favorite", "like"],
    "kuaishou": ["favorite", "like"],
    # **不再采浏览历史**（Owner 2026-08-12 定：「先停历史，点赞留着」）。
    #
    # 他库里 56 篇「标题是播放进度」全部来自 history 这条路——历史页的形状读取
    # 挑中了每行的播放进度元素而不是标题。那 56 篇已经用 B 站公开接口修回真标题；
    # 停掉 history 之后**根源也没了**：不再有新的历史条目进来，
    # 于是「要定位真标题在哪个元素上」那件活（需要他登录后的历史页）**不用干了**。
    #
    # 已经存下的历史条目**一条不删**——归档的意义就是东西留下来。
    # 只是不再新增。
    "bilibili": ["favorite", "watch_later", "like"],
    "x": ["bookmark", "like"],
    "reddit": ["saved", "upvoted"],
    "instagram": ["saved"],
    # YouTube 的「稍后观看」与播放列表都要登录态才看得见，正是托管凭据的用武之地。
    "youtube": ["watch_later", "playlist"],
    "generic-web": ["bookmark", "manual_save"],
}

# **允许**出现 ≠ **能去枚举**。
#
# 这些关系类型可以合法地存在于库里，但一次同步没法把它们"列出来"——
# 没有任何平台页面能回答"我手动存过哪些"。把它们算进同步范围，
# 那一路就永远等不到终批，整次 run 永远不收敛。
#
# 实测（本机真实 Chrome，首次连接 Chrome 书签）：62 条全部入库，
# 运行状态却停在 scanning 不动，因为 relation_scope 是
# ['bookmark', 'manual_save'] 而扩展只送 bookmark 的终批。
# 界面上就是「点了同步，东西都进来了，圈还一直在转」。
NON_SCANNABLE_RELATIONS: frozenset[str] = frozenset({"manual_save"})


def _scannable_relations_doc() -> None:
    """扩展真正会去枚举的关系——**真源是扩展那一份，不在这里再抄一遍**。（2026-08-10）

    ## 它修的是什么

    `_scannable_relations` 原来 = 「这个平台允许出现的关系」减去 `manual_save`。
    而 `_relations` 自己的文档串就写着：**「用于校验批次，不是同步范围。」**

    扩展只扫 `SCANNABLE_RELATIONS`（抖音/小红书/快手/B站都只有 `favorite`），
    服务端却把「允许」的全列进 scope。于是 scope 里那些扩展不会扫的关系
    **永远等不到终批**——而这个文件自己的注释早就写过那种后果：
    「点了同步，条目都进来了，圈还一直在转」，这次 run 永远不收敛。

    Owner 的生产数据正是这个形状：**20 次同步、0 次 completed**
    （partial 16 / failed 3 / cancelled 1），最常见的错误码是
    `RELATION_SCOPE_UNCONFIRMED`（8 次）。逐条查 sync_run_scope：
    抖音每次都声明 `favorite` + `like`，B 站声明 `favorite` + `watch_later` + …，
    **没有一条 scope 的 completeness 是 complete**。

    account_sync.py 里那句注释写着「由 platform-catalog.js 的
    SCANNABLE_RELATIONS 限定扫描范围」——**而服务端从来没读过那个文件。**

    ## 为什么读文件而不是再抄一份

    这个仓当天已经因为「同一件事两份词典必然漂开」修过三处
    （失败文案、归档状态、回执键名）。抄第四份只是把问题推后。

    ## 第一版是 import 时去读那个 .js —— **它让 API 起不来**

    `Path(__file__).resolve().parents[2] / "apps/browser-extension/..."`
    在仓里正好是仓根，跑得好好的；**装进镜像之后 `parents[2]` 是
    `/usr/local/lib/python3.12/`**，文件不存在，而我又特意写了「读不到就抛」：

        FileNotFoundError: '/usr/local/lib/python3.12/apps/browser-extension/
                            content/platform-catalog.js'

    入口点 `social-archive-api` 当场死在 import 上。那一刻 1402 条判据全绿——
    **因为判据全跑在仓里**。抓到它的是把镜像真起一次，不是读代码。

    所以改成**生成**：`.js` 仍是唯一真源，
    `scripts/generate_scannable_relations.py` 把它编译成
    `social_archive/scannable_relations.py`（纯字面量，跟着包装，无相对路径）。
    两边漂开由判据当场打红，并在错误里给出重新生成的命令。
    """


from .scannable_relations import SCANNABLE_RELATIONS

PLATFORM_LABELS = {
    "xiaohongshu": "小红书",
    "douyin": "抖音",
    "kuaishou": "快手",
    "bilibili": "B站",
    "x": "X",
    "reddit": "Reddit",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "generic-web": "通用网页",
}

# These platforms can be attempted by the server-side prebuilt adapters. Other
# platforms use the extension/isolated-worker batch protocol as the primary free
# path; the product never asks the owner to paste cookies or headers.
# v0.0.0.7 / G1：**bilibili 从这里移走。**
#
# 它留在这张表里是一处结构性矛盾，而不只是一个没做完的连接器：
# 服务端那条路（CommandArtifactConnector → bilibili-cli sidecar）要拿到
# Owner 的 B 站登录态才跑得动，而 `cookie-export.js` 的
# `FORBIDDEN_PLATFORMS = {xiaohongshu, douyin, bilibili, kuaishou}`
# 规定这四个平台的 Cookie **永远不出浏览器**（INV-DOMESTIC-COOKIE-STAYS）。
# 也就是说服务端**永远拿不到**它需要的东西——这条路不是"还没做完"，是"不许做"。
#
# 后果不是抽象的：extension 的 runBrowserAccountSync 先看 canSync 再看
# serverHandled，一旦 bilibili 进了 SYNCABLE_NOW，serverHandled=True 会把它
# 从**能跑通的浏览器路**踢到**永远跑不通的服务端路**上去。
# v0.0.0.22：reddit / instagram 移出去了。它们的主路径是**扩展读取**
# （Owner 给的平台表里就是这么写的），而服务端这条 2026-08-04 打生产量出来
# 两条都不通。留在这张表里的后果不是中性的：runBrowserAccountSync 见到
# server_handled=true 就不参与，等于把它们钉死在那条不通的路上。
SERVER_ACCOUNT_CONNECTORS = {"x"}

#: 服务端**也能**自己读的平台（2026-08-17）。
#
# **和上面那个集合不是一回事，这一点是花了一次回归换来的。**
# 第一版直接把 bilibili 加进 SERVER_ACCOUNT_CONNECTORS —— 那会让
# **所有** B 站的 run 都改走服务端路，于是扩展送来的批没人收了，
# `bilibili_end_to_end_drill` 当场红：「档案馆只收到 0 条，应该是 3 条」。
#
# 服务端这条路是**增加**的一条，不是替换：浏览器那条路原样不动
# （它能读私密收藏夹，服务端读不到），只有调度器发起的那种 run
# 才走服务端。两条各自独立，互不接管。
SERVER_ALSO_READS = {"bilibili"}

#: 调度器发起服务端读取时用的 trigger_type。process_job 据此选路 ——
#: **按这次 run 是谁发起的选，不按平台选**。
SERVER_PUBLIC_TRIGGER = "scheduled_server"

# **本版本真的同步得动的平台。** 这不是「支持哪些平台」的愿景清单，
# 是「现在点下去会成功」的事实清单。
#
# 为什么必须有它：小红书 / 抖音 / 快手 / B站 走浏览器拦截路，而那条路的
# 取数缝隙 acquireRelationItems() 目前是显式 stub（T03 删掉 DOM 抓取器之后，
# T08 的替代品还没缝上）。界面却照样给它们画「立即同步」按钮，点下去拿到的是
# ACQUISITION_PATH_NOT_INSTALLED —— 而那个码被别名成 SERVER_UNREACHABLE，
# 于是用户看到「暂时连不上服务器，[ 重试 ]」，**一遍遍重试一件永远不可能成功的事**。
#
# Owner 的原话：「非常不好用，而且你的流程逻辑非常混乱，我都不知道应该怎么操作。」
# 直接原因就是这个：界面提供了一个结构上不可能成功的动作。
#
# 规则：**能不能同步是服务端说了算，界面照着画**。不要在两个前端各维护一份。
# 2026-08-04 生产实测把这张表砍到只剩一个。三条都是**打到生产上量出来的**，
# 不是读代码推的（POST /v1/connectors/{id}/run）：
#
#   x          blocked_environment  X_ZERO_COST_NOT_CONFIRMED
#              官方 X API 被零费用门关着（默认 false，Owner 的 L0 硬边界是
#              「0 新增必付费用」）。账号同步走的是同一条 registry.run，
#              所以**本版本没有任何一条 x 取数路能成**。
#              旁边原来那行注释写着「Cookie 托管 + gallery-dl（T06/T07）」
#              ——那是意图，代码没有实现它。
#   reddit     blocked_environment  REDDIT_AUTH_MISSING「缺少 Reddit OAuth token 或 username」
#              配置项确实"设得上"（写进 /run/secrets/reddit_oauth_token），
#              但那要有服务器访问权限、要会编辑文件。**Owner 说过「我没有技术基础」。**
#              没有界面，没有 OAuth 授权入口。
#   instagram  HTTP 422「CLI Sidecar 调用失败」——连结构化失败都不是。
#
# 三个平台的界面上都画着「立即同步」。点下去分别得到
# 「零费用门未确认」「缺少 Reddit OAuth token 或 username」「HTTP 422」。
# 这正是 Owner 那句「点击同步不就是自动刷新全部同步吗，怎么实际功能和
# 显示文字还不一样」，只是他还没连上这三个所以没撞到。
#
# **这张表是事实清单，不是愿景清单。** 量不出来的就不许留在里面。
SYNCABLE_NOW: frozenset[str] = frozenset({
    # Chrome 书签。T04 量到 62 条全量入库——**但那是在演练里**，
    # 而演练在加载扩展前把可选权限全提成了必给权限。2026-08-06 去生产上查：
    # 他的库里**根本没有 generic-web 账号**。那 62 条只存在于演练里。
    #
    # 留在这张表里仍然是对的：机制是真的，权限申请挪到扩展页面之后
    # （v0.0.0.22）那颗按钮才第一次真的能成。但**别再把它说成"他那边跑通过"**。
    "generic-web",
    # v0.0.0.7 / G1（2026-08-06）：B 站收藏夹。取数在 Owner 自己的浏览器里，
    # 调 B 站自己的公开 REST 接口（apps/browser-extension/content/bilibili-reader.js）。
    # 零费用、不要他粘任何东西、Cookie 不出浏览器。
    #
    # 进这张表的凭据是**打真实接口量出来的**，不是读文档推的：
    #   GET /x/v3/fav/folder/created/list-all → 收藏夹清单（权威来源）
    #   GET /x/v3/fav/resource/list           → 条目，翻页终点由接口自己的
    #                                           has_more 决定，再和 info.media_count 对账
    #   CORS：Origin 为 www/space.bilibili.com 时回 allow-credentials: true
    # 实测一个 10 条的公开收藏夹：声明 10 / 读到 10 / 翻 3 页 / 跳过 0。
    #
    # **本版本只读「收藏夹」这一种关系。** 稍后再看/历史/点赞的取数路没做，
    # 由 platform-catalog.js 的 SCANNABLE_RELATIONS 限定扫描范围——
    # 不写进那张表就等于不承诺，界面也不会假装它们会被同步。
    "bilibili",
    # v0.0.0.21：小红书 / 抖音 / 快手。取数走「按形状认页面自己发的列表」
    # （content/list-shape.js + net-observer 的无前缀模式）。
    #
    # **它和 B 站那条的证据强度不一样，这里说清楚：**
    #   B 站    —— 打过真接口，声明 10 条读到 10 条
    #   这三个  —— 机制在**真 Chrome + 假站**上跑通（抓到 5 条响应、
    #              正确认出收藏列表而不是推荐流、7 条全部拿到可打开的网址），
    #              但**没有验过真平台的响应长什么样**——那需要 Owner 的登录态。
    #
    # 那为什么还是打开：验收标准禁的是「结构上不可能成功的按钮」。
    # 旧的那个 stub 是结构上不可能（抛 ACQUISITION_PATH_NOT_INSTALLED）；
    # 这条路结构上是通的，剩下的是「这个平台的形状认不认得出」——
    # **认不出时它会明确说出来**（LIST_SHAPE_NOT_RECOGNISED，
    # 文案告诉他去收藏页并往下滚），不会静默、不会丢数据
    # （只报 partial，不触发消失检测）。
    "xiaohongshu",
    "douyin",
    # **快手不在这里了**（Owner 2026-08-12 定：「明确不做，改成只能手动保存」）。
    #
    # 它原先和小红书/抖音同级挂在这里，理由是「机制在真 Chrome + 假站上跑通」。
    # 但真平台的字段名一直没验过：公开页推断失败过一次——我在真实载荷里
    # 找到的 `userName` 后来发现是遥测 Cookie 名，不是 feed 字段。
    #
    # 挂在「能自动」里而实际取不到，就是验收条件第 1 条说的
    # 「一颗结构上不可能成功的按钮」。宁可当场说清「这个只能手动保存」。
    # v0.0.0.22：Reddit / Instagram 换到同一条路上。
    #
    # 它们原先挂在服务端连接器上，而 2026-08-04 打生产量出来两条都不通
    # （reddit 缺授权、instagram 的 Sidecar 调用回 422）。**服务端那条
    # 从来就不是主路径**——Owner 给的平台表里，这两个写的是「扩展读取 / 导出导入」。
    #
    # 让它们走得通的是同一天修掉的那个缺陷：识别器原先只看元素**自己身上**的
    # 字段，而这两家的 id 都藏在壳里（`children[].data.id`、`items[].media.pk`），
    # 于是「0% 的元素带得出 id」，一条都认不出。
    #
    # **证据强度和上面三个同级**：机制在真 Chrome + 假站上跑通，
    # 真平台的响应长什么样没验过——那要 Owner 的登录态。
    # 认不出时它明确说得出来，不会静默也不会丢数据。
    "reddit",
    "instagram",
})
# 暂时同步不了的，每条写清**为什么**与**现在能做什么**。
# 界面直接把这句话显示出来，而不是让用户点了才知道。
NOT_SYNCABLE_YET: dict[str, str] = {
    # 2026-08-12 由 Owner 裁定：快手明确不做自动读取。
    #
    # 取数那条路要的是「快手收藏页返回的 JSON 里，标题/作者/链接各叫什么」。
    # 那三个字段名只能从他登录后的真实响应里读出来；公开页推断试过一次，
    # 拿到的 `userName` 其实是遥测 Cookie 名——**推断出来的字段名是假的**。
    # 与其挂在「能自动」里给一颗点了取不到东西的按钮，不如现在就说清楚。
    "kuaishou": "本版本不自动读取快手的收藏。取数需要的那几个字段名只能从你登录后的"
                "真实响应里确认，靠公开页推断出来的是假的，所以这条路先不开。"
                "现在可以：在浏览器里打开任意一条快手内容，点插件的「保存当前页面」，"
                "这一条就会进档案馆。",
    # 2026-08-05 由 Owner 裁定接上 youtube 的入口。**能连不等于能同步**：
    # 凭据托管那条路是通的（服务端凭据表、Cookie 导出白名单一直都支持它），
    # 而「把稍后观看/播放列表列出来」那条取数路一行都没写。
    # 所以它进这张表，和别的「还不能」的平台一样，一句话说清现在能做什么。
    # **「连接 YouTube」要说清点哪儿——而这句话就显示在那张卡片上。**
    #
    # 2026-08-05：我在 registry 的 CONNECT_IS_CLICKABLE_TODAY 里写了一句
    # 很详细的「点插件图标 → 设置 → 找到 YouTube → 点连接账号」，
    # 然后发现**没有任何界面读那个字段**（连接器卡片显示的是这里的
    # not_syncable_reason）。那句话写完就是隐形的——同一天第二次踩这个坑。
    #
    # 而这句话恰恰显示在 YouTube 那张卡片的正文里，「连接账号」按钮就在
    # 同一张卡的下沿。所以不必描述路径，直接指那颗按钮。
    "youtube": (
        "本版本还不能自动读取 YouTube 的稍后观看和播放列表。"
        "现在可以：点这张卡片上的「连接账号」，把登录状态交给你自己的服务器保管；"
        "以及在任意视频页点插件保存当前这一条。"
    ),
    # bilibili 已于 2026-08-06（G1）移出这张表 —— 它现在在 SYNCABLE_NOW 里。
    # **这一行不要再加回来**：两张表同时提到同一个平台时，界面读的是
    # sync_supported（来自 SYNCABLE_NOW），而 not_syncable_reason 会照样显示，
    # 于是卡片上会出现「立即同步」按钮 + 「本版本还不能自动读取」两句自相矛盾的话。
    # 下面三条的原因和上面四个不一样：上面四个是「取数路还没做出来」，
    # 这三个是「路做了一半，而剩下那半不是你能补上的」。
    # 文案里不出现「OAuth」「token」「sidecar」——Owner 说过他没有技术基础，
    # 让他读这些词等于让他读我们的代码。
    "x": "本版本还不能自动读取 X 的书签。原因是官方 X 接口可能收费，"
         "而这个项目的硬规矩是绝不产生新的必付费用，所以那条路是主动关着的。"
         "现在可以：在浏览器里打开任意一条推文，点插件的「保存当前页面」。",
}


@dataclass(frozen=True)
class ConnectStartResult:
    connection_ref: str
    platform: str
    auth_method: str
    state: str
    next_action_zh: str
    supported_relations: list[str]


class AccountSyncCoordinator:
    def __init__(
        self,
        settings: Settings,
        store: RuntimeStore,
        archive: ArchiveService,
        registry: ConnectorRegistry,
    ) -> None:
        self.settings = settings
        self.store = store
        self.archive = archive
        self.registry = registry

    @staticmethod
    def _relations(platform: str, requested: list[str] | None = None) -> list[str]:
        """该平台**允许**出现的关系类型。用于校验批次，不是同步范围。"""
        allowed = PLATFORM_RELATIONS.get(platform, [])
        if not requested:
            return list(allowed)
        return [item for item in dict.fromkeys(requested) if item in allowed]

    @staticmethod
    def _scannable_relations(platform: str, requested: list[str] | None = None) -> list[str]:
        """一次同步**能去枚举**的关系类型 —— 与「允许」不是一回事。

        `manual_save` 是"用户自己手动存的这一条"（CaptureRequest 的默认值）。
        它必须是**允许**的关系类型，否则手动收藏会被拒；
        但它**不可枚举**：没有任何平台页面能列出"我手动存过哪些"。

        把它放进同步范围的后果，实测于本机真实浏览器：

            首次连接 Chrome 书签 → 62 条全部入库 → 运行状态却永远停在
            `scanning`，因为 relation_scope 是 ['bookmark', 'manual_save']
            而扩展只会送 bookmark 的终批，manual_save 那一路永远等不到，
            于是这次 run 永远不收敛。

        界面上就是：**点了同步，62 条都进来了，圈还一直在转。**
        这正是这一版要消灭的那种「说不清楚发生了什么」。
        """
        # **范围 = 扩展真会扫的 ∩ 这个平台允许的**。（2026-08-10）
        # 原来只减掉 manual_save，于是把「允许」当成了「会扫」——
        # scope 里那些扩展不扫的关系永远等不到终批，run 永远不收敛。
        # 平台不在那张表里时退回旧行为：它本来就没有「按形状读」这条路。
        scannable = SCANNABLE_RELATIONS.get(platform)
        return [
            item for item in AccountSyncCoordinator._relations(platform, requested)
            if item not in NON_SCANNABLE_RELATIONS
            and (scannable is None or item in scannable)
        ]

    def connect_start(self, request: AccountConnectRequest) -> ConnectStartResult:
        platform = request.platform.strip().lower()
        if platform not in PLATFORM_RELATIONS:
            raise ValueError("当前平台不在本版本账号同步范围内")
        connection_ref = f"conn_{secrets.token_urlsafe(24)}"
        method = request.auth_method
        action = {
            "oauth": "将在平台官方授权页确认只读权限。",
            "qr": "请在弹出的平台登录窗口扫码；完成后自动返回。",
            "browser_session": "请在当前 Chrome 中登录该平台，然后点击“我已登录”。",
            "official_export": "请选择平台官方导出的数据文件；系统会自动识别。",
            "local_import": "请选择现有归档文件；系统会自动去重导入。",
            "chrome_bookmarks": "请授权读取 Chrome 书签；不会读取浏览历史。",
        }[method]
        # No credential is persisted here. The opaque ref is exchanged only after
        # a real environment verifies the login/session.
        return ConnectStartResult(
            connection_ref=connection_ref,
            platform=platform,
            auth_method=method,
            state="authorizing",
            next_action_zh=action,
            supported_relations=self._relations(platform, request.relation_types),
        )

    def complete_connection(
        self,
        *,
        platform: str,
        auth_method: str,
        connection_ref: str,
        external_account_id: str,
        display_name: str | None,
        auto_sync_enabled: bool,
        sync_interval_minutes: int,
        metadata: dict[str, Any],
        verified: bool,
    ) -> str:
        if not verified:
            raise ValueError("只有完成真实登录验证后才能标记账号已连接")
        if not connection_ref.startswith("conn_"):
            raise ValueError("连接凭据无效，请重新连接账号")
        if not 15 <= sync_interval_minutes <= 10080:
            raise ValueError("账号同步间隔必须在 15–10080 分钟")
        # **同一个平台再连一次，认领已有的那个账号，别开第二个。**
        #
        # 2026-08-07 在 Owner 生产库里量到的形状：他三个账号的
        # external_account_id 是**主页地址**（上一代取数路留下的）——
        #     xiaohongshu  https://www.xiaohongshu.com/user/profile/68f8b613…
        #     douyin       https://www.douyin.com/user/self?from_nav=1
        #     bilibili     https://space.bilibili.com/3493091105311656
        # 而按形状读那条路认不出他是谁（它只读收藏页，不去主页），
        # 完成连接时报的是固定的 "browser-session"。
        #
        # 两者对不上，于是**重连会新建一行**：他的 85 条抖音、102 条 B 站
        # 留在旧账号下面，新卡片上写着 0 条。数据没丢，但他看到的是"东西没了"。
        #
        # 所以：这个平台已经有一个同样连接方式的账号时，沿用它的外部 id。
        # 沿用而不是改写，是因为 `user_relation.source_account_id` 是从
        # 外部 id 推出来的——改写它等于把已有条目和账号的关系割断。
        # **2026-08-10：条件比上面那条规则窄了一档，而差的那一档正好是 B 站。**
        #
        # 规则写的是「这个平台已经有一个同样连接方式的账号时，沿用它的外部 id」，
        # 而代码只在外部 id 恰好是哨兵值 `"browser-session"` 时才执行。
        # 小红书 / 抖音 / 快手按形状读，认不出用户是谁，报的就是哨兵值——它们没事。
        # **B 站不是**：它走 B 站自己的接口，认得出用户，报的是 mid
        # （background.js `external_account_id: String(who.mid)`）。
        #
        # 对着他生产库量出来的两个值：
        #     库里那一行  acct_dd40c2f3… ← 'https://space.bilibili.com/3493091105311656'
        #     重连会报的                   '3493091105311656'
        # 不相等、也不是哨兵值 → 认领整个跳过 → 另算出一个账号 id →
        # 多一行 B 站账号、卡片写着 0 条，而他那 **103 条内容和 3 行收藏夹**
        # 留在旧账号名下。**这发生在他照着说明做那唯一一件事的那一刻。**
        #
        # 所以改成按**连接方式**认领。Chrome 书签走 `chrome_bookmarks`，不受影响；
        # 哨兵值那条继续留着，免得将来别的连接方式也用它。
        # 取数不受影响：B 站的 mid 是同步时从 nav 接口现拿的
        # （bilibili-reader.js `whoAmI()`），从来不读这个字段。
        if auth_method == "browser_session" or external_account_id == UNIDENTIFIED_BROWSER_ACCOUNT:
            existing = self.store.find_source_account_by_platform(
                platform=platform, auth_method=auth_method)
            if existing and existing.get("external_account_id"):
                external_account_id = str(existing["external_account_id"])
        account_id = self.store.upsert_source_account(
            platform=platform,
            external_account_id=external_account_id,
            display_name=display_name,
            auth_method=auth_method,
            auth_handle_ref=connection_ref,
            connection_state="connected",
            auto_sync_enabled=auto_sync_enabled,
            sync_interval_minutes=sync_interval_minutes,
            metadata=metadata,
        )
        return account_id

    def start_sync(self, account_id: str, request: AccountSyncRequest) -> dict[str, Any]:
        account = self.store.get_source_account(account_id, include_handle=True)
        if not account:
            raise ValueError("账号不存在")
        if account["connection_state"] not in {"connected", "degraded"}:
            raise ValueError("账号尚未连接，请先完成授权")
        relations = self._scannable_relations(account["platform"], request.relation_types)
        if not relations:
            # **界面不发的请求，服务端也不该接受。**（2026-08-10）
            #
            # YouTube 落在这一档：它的取数路没做，界面早就照 SYNCABLE_NOW
            # 把「立即同步」按钮收起来了。但服务端这一侧原本仍会按
            # PLATFORM_RELATIONS 下发 ['watch_later','playlist']——
            # 扩展一条都不会去扫，那次 run 就永远等不到终批
            # （他抖音那二十次「点了同步，圈一直转」正是这个形状）。
            # **不能靠界面替服务端守不变量。**
            #
            # 话用 NOT_SYNCABLE_YET 里那一句，不另编一句：同一件事两处措辞
            # 必然漂开，这个仓当天已经因为「两份词典」修过四处。
            platform = account["platform"]
            label = PLATFORM_LABELS.get(platform, platform)
            raise ValueError(
                NOT_SYNCABLE_YET.get(platform)
                or f"本版还不能自动读 {label}——它的取数路还没做。")
        mode = request.mode
        if mode == "incremental" and not account.get("last_sync_at"):
            mode = "first_full"
        run_id = self.store.create_sync_run(
            source_account_id=account_id,
            platform=account["platform"],
            mode=mode,
            relation_types=relations,
            trigger_type=request.trigger_type,
        )
        job_id = self.store.enqueue_job(
            "account_sync",
            {"sync_run_id": run_id, "account_id": account_id, "relations": relations, "mode": mode},
            connector_id=account["platform"],
        )
        return {
            "sync_run_id": run_id,
            "job_id": job_id,
            "status": "queued",
            "mode": mode,
            "relations": relations,
            "next_action_zh": "首次同步已开始；已完成内容会立即出现在资料库。" if mode == "first_full" else "增量同步已开始。",
        }

    def process_job(self, payload: dict[str, Any]) -> None:
        run_id = str(payload["sync_run_id"])
        account_id = str(payload["account_id"])
        run = self.store.get_sync_run(run_id)
        account = self.store.get_source_account(account_id, include_handle=True)
        if not run or not account:
            raise ValueError("同步运行或账号不存在")
        # **终态就是终态，别把它翻出来重跑。**
        #
        # 这一组原来少了 `blocked_environment`——而 db.py 那边把它算作终态
        # （`completed = status in {..., "blocked_environment"}`，会写 completed_at）。
        # 实测（2026-08-06）：把一个 run 打到 blocked_environment、账号此刻仍然连着，
        # 再投一次同一个任务，**它真的往下跑到连接器去了**。也就是说一个已经
        # 报给用户「被环境挡住了」、而且已经盖了完成时间的运行，会被悄悄重跑一遍。
        #
        # 从阻塞里出来的正当路子是**用户点重试**：db.py 的 retry 迁移
        # （`{partial, failed, blocked_environment} → queued`）会把它重新排队，
        # 那时 status 是 queued，这里自然就放行了。
        if run["status"] in {"cancelled", "completed", "partial", "failed",
                             "blocked_environment"}:
            return
        if account["connection_state"] not in {"connected", "degraded"}:
            self.store.update_sync_run(run_id, status="blocked_environment", completeness="unknown", error_code="ACCOUNT_REAUTH_REQUIRED", error_message="账号需要重新连接")
            return

        platform = account["platform"]
        relations = list(run.get("relation_scope") or payload.get("relations") or PLATFORM_RELATIONS.get(platform, []))
        server_side = (platform in SERVER_ACCOUNT_CONNECTORS
                       or (platform in SERVER_ALSO_READS
                           and str(run.get("trigger_type") or "") == SERVER_PUBLIC_TRIGGER))
        if not server_side:
            # The extension/isolated worker owns browser-session scanning. Keeping
            # the run in scanning state makes the next action explicit without
            # pretending a server-only connector succeeded.
            self.store.update_sync_run(
                run_id,
                status="scanning",
                completeness="unknown",
                evidence={"ingest_mode": "extension_or_isolated_worker", "waiting_for_batch": True},
            )
            return

        self.store.update_sync_run(run_id, status="discovering")
        imported_total = 0
        failed_total = 0
        discovered_total = 0
        partial = False
        blocked_environment = False
        last_failure_code: str | None = None
        max_items = self.settings.account_sync_max_items_per_run
        for relation in relations:
            current = self.store.get_sync_run(run_id)
            if current and current["status"] in {"paused", "cancelled"}:
                return
            self.store.update_sync_run(run_id, status="scanning")
            checkpoint = self.store.get_sync_checkpoint(
                source_account_id=account_id,
                relation_type=relation,
                collection_key="",
            )
            checkpoint_cursor = (checkpoint or {}).get("cursor") or {}
            cursor_key = "next_cursor"
            cursor_value = checkpoint_cursor.get(cursor_key)
            if not cursor_value:
                cursor_key = "next_token"
                cursor_value = checkpoint_cursor.get(cursor_key)
            cursor = str(cursor_value).strip() if cursor_value else None
            resumed_from_prior_run = bool(cursor)
            seen_cursors = {cursor} if cursor else set()
            observed_relation_ids: set[str] = set()
            known_anchor: str | None = None

            while True:
                current = self.store.get_sync_run(run_id)
                if current and current["status"] in {"paused", "cancelled"}:
                    return
                remaining = max_items - discovered_total
                if remaining <= 0:
                    partial = True
                    last_failure_code = "ACCOUNT_SYNC_ITEM_LIMIT_REACHED"
                    resume_cursor = {cursor_key: cursor} if cursor else {}
                    self.store.upsert_sync_checkpoint(
                        source_account_id=account_id,
                        relation_type=relation,
                        collection_key="",
                        cursor=resume_cursor,
                        known_anchor=known_anchor,
                        last_complete_sync_run_id=None,
                        complete=False,
                    )
                    self.store.update_sync_run(
                        run_id,
                        error_code=last_failure_code,
                        error_message="本次同步达到安全条目上限；已保留检查点。",
                        cursor={"relation": relation, **resume_cursor},
                    )
                    break

                request = ConnectorRunRequest(
                    relation_type=relation,  # type: ignore[arg-type]
                    limit=min(self.settings.account_sync_page_size, remaining),
                    source_account_id=account["external_account_id"],
                    cursor=cursor,
                    requested_levels=["L0", "L1", "L3"],
                    destination_ids=["social_archive", "markdown"],
                )
                result, captures = self.registry.run(platform, request)
                responses = []
                for capture in captures:
                    effective = capture.model_copy(update={
                        "source_account_id": account["external_account_id"],
                        "raw_metadata": {**capture.raw_metadata, "sync_run_id": run_id},
                    })
                    response = self.archive.capture(effective)
                    responses.append(response)
                    observed_relation_ids.add(response.relation_id)
                if known_anchor is None and captures:
                    known_anchor = captures[0].external_content_id

                receipt = dict(result.scan_receipt)
                receipt.setdefault("scope", "account_relation")
                receipt.setdefault("relation_type", relation)
                receipt.setdefault("source_account_id", account["external_account_id"])
                if cursor:
                    receipt.setdefault("cursor_start", cursor)
                page_discovered = max(int(receipt.get("item_count") or len(captures)), len(captures))
                discovered_total += page_discovered
                failed_total += len(result.errors)
                blocked_environment = blocked_environment or result.status == "blocked_environment"

                complete = receipt.get("completeness") == "complete"
                next_cursor_key = "next_cursor" if receipt.get("next_cursor") else "next_token"
                next_value = receipt.get(next_cursor_key)
                next_cursor = str(next_value).strip() if next_value else None
                if next_cursor:
                    cursor_key = next_cursor_key
                failure_code = str(receipt.get("failure_code") or (result.errors[0].get("code") if result.errors else "") or "") or None
                resume_cursor: dict[str, Any] = {}
                continue_paging = False

                if complete and resumed_from_prior_run:
                    # A cursor recovered from an earlier run proves continuation,
                    # not a complete current-run relation snapshot. Never close
                    # older relations until one fresh scan observes every page.
                    complete = False
                    partial = True
                    failure_code = f"{platform.upper().replace('-', '_')}_FRESH_FULL_SCAN_REQUIRED"
                    receipt["completeness"] = "partial"
                    receipt["failure_code"] = failure_code
                elif complete:
                    self.store.apply_complete_scan(
                        platform,
                        observed_relation_ids,
                        relation_type=relation,
                        source_account_id=account["external_account_id"],
                    )
                elif next_cursor and discovered_total < max_items and next_cursor not in seen_cursors:
                    resume_cursor = {cursor_key: next_cursor}
                    continue_paging = True
                else:
                    partial = True
                    if next_cursor:
                        if discovered_total >= max_items:
                            resume_cursor = {cursor_key: next_cursor}
                            failure_code = "ACCOUNT_SYNC_ITEM_LIMIT_REACHED"
                            receipt["failure_code"] = failure_code
                        elif next_cursor in seen_cursors:
                            resume_cursor = {cursor_key: cursor or next_cursor}
                            failure_code = f"{platform.upper().replace('-', '_')}_CURSOR_LOOP"
                            receipt["failure_code"] = failure_code
                    elif cursor:
                        resume_cursor = {cursor_key: cursor}

                if failure_code:
                    last_failure_code = failure_code
                self.store.record_scan_receipt(
                    platform,
                    result.run_id,
                    receipt,
                    source_account_id=account["external_account_id"],
                    relation_type=relation,
                )
                imported_total += len(responses)
                self.store.upsert_sync_checkpoint(
                    source_account_id=account_id,
                    relation_type=relation,
                    collection_key="",
                    cursor={} if complete else resume_cursor,
                    known_anchor=known_anchor,
                    last_complete_sync_run_id=run_id if complete else None,
                    complete=complete,
                )
                self.store.update_sync_run(
                    run_id,
                    discovered_delta=page_discovered,
                    imported_delta=len(responses),
                    failed_delta=len(result.errors),
                    error_code=failure_code,
                    error_message=(result.errors[0].get("message") if result.errors else None),
                    cursor={"relation": relation, **({} if complete else resume_cursor)},
                )
                if not continue_paging:
                    break
                cursor = next_cursor
                seen_cursors.add(cursor)
        final_status = "blocked_environment" if blocked_environment else ("partial" if partial or failed_total else "completed")
        self.store.update_sync_run(
            run_id,
            status=final_status,
            completeness="unknown" if final_status == "blocked_environment" else ("partial" if final_status == "partial" else "complete"),
            error_code=last_failure_code,
            evidence={"imported": imported_total, "failed": failed_total, "completed_at": utcnow()},
        )
        if final_status != "blocked_environment":
            self.store.set_source_account_state(account_id, "connected", verified=True)
        if final_status == "completed":
            with self.store.connection() as con:
                con.execute("UPDATE source_account SET last_sync_at=?,updated_at=? WHERE id=?", (utcnow(), utcnow(), account_id))

    def _finalize_relation_scope(
        self,
        *,
        sync_run_id: str,
        run: dict[str, Any],
        account: dict[str, Any],
        relation_type: str,
        completeness: str,
        failure_code: str | None,
        errors: list[dict[str, Any]],
        discovered_delta: int = 0,
        imported_delta: int = 0,
    ) -> tuple[str, int]:
        """Close one relation only after an explicit relation-final marker.

        Page/collection batches never close the run. The observed relation IDs are
        accumulated across every chunk, so a final page cannot make earlier pages
        look deleted. A complete marker evaluates every previously known collection,
        including collections that became empty during this sync.
        """
        effective_completeness = completeness
        if errors and effective_completeness == "complete":
            effective_completeness = "partial"
        scope_status = {
            "complete": "complete",
            "partial": "partial",
            "failed": "failed",
            "unknown": "partial",
        }[effective_completeness]

        closed_candidates = 0
        if effective_completeness == "complete":
            collections = self.store.list_sync_seen_collections(
                sync_run_id=sync_run_id,
                relation_type=relation_type,
            )
            # **只有平台确认存在过的收藏夹才可能"变空"。**
            #
            # 库里挂着某个 key 不等于那是一个收藏夹——它可能是**上一代取数路
            # 留下的写法**。2026-08-06 在 Owner 生产库里量到：30 条 B 站收藏挂在
            # `bilibili:/3493091105311656/favlist` 上（T03 删掉的 DOM 抓取器留的），
            # 而现在这条路用媒体 id。不加这道交集的话，那个旧 key 会被当成
            # 「一个变空了的收藏夹」，重连之后两次同步就把**他 30 条收藏销账**。
            #
            # 登记过（platform_collection 里有名字）的才算数：真被他删掉的收藏夹
            # 一定登记过，所以「变空要关掉」那个本意一点没丢。
            registered = self.store.list_registered_collections(
                platform=account["platform"],
                external_account_id=account["external_account_id"],
                relation_type=relation_type,
            )
            collections.update(self.store.list_existing_relation_collections(
                platform=account["platform"],
                external_account_id=account["external_account_id"],
                relation_type=relation_type,
            ) & registered)
            if not collections:
                collections.add("")
            # **同一次同步里，一个收藏夹只许记一次缺席。**
            #
            # `apply_complete_scan` 有两个调用点：收藏夹级终批一个（下面 ingest 那段），
            # 关系级终批这里一个。两边都跑的话，一次同步就给同一条关系记了**两次**缺席
            # ——而"连续两次缺席才关闭"这个安全设计的全部意义，就是让**一次**读漏
            # （网络抖动、翻页卡住）不至于销账。两次并作一次，那道保险等于没有。
            #
            # v0.0.0.9 之前这条路是死的（DOM 抓取器删掉后没人发收藏夹级终批），
            # 所以一直没暴露。B 站改成按收藏夹分批之后它立刻活了：
            # 判据 test_a_real_unfavourite_does_close_after_two_complete_scans
            # 在 per_collection=True 那一档当场变红——**取消收藏后一次同步就销账**。
            already_scanned = {
                str(scope["collection_key"])
                for scope in self.store.list_sync_run_scopes(sync_run_id)
                if scope["collection_key"] not in {"__relation__", "__mixed__"}
                and scope.get("completeness") == "complete"
            }
            for collection_key in collections:
                if collection_key in already_scanned:
                    continue
                observed = self.store.list_sync_seen_relation_ids(
                    sync_run_id=sync_run_id,
                    relation_type=relation_type,
                    collection_key=collection_key,
                )
                closed_candidates += self.store.apply_complete_scan(
                    account["platform"],
                    observed,
                    relation_type=relation_type,
                    collection_key=collection_key,
                    source_account_id=account["external_account_id"],
                )

        self.store.upsert_sync_run_scope(
            sync_run_id=sync_run_id,
            relation_type=relation_type,
            collection_key="__relation__",
            status=scope_status,
            completeness=effective_completeness,
            discovered_delta=discovered_delta,
            imported_delta=imported_delta,
            failed_delta=len(errors),
        )
        self.store.upsert_sync_checkpoint(
            source_account_id=account["id"],
            relation_type=relation_type,
            collection_key="__relation__",
            cursor={},
            known_anchor=None,
            last_complete_sync_run_id=sync_run_id if effective_completeness == "complete" else None,
            complete=effective_completeness == "complete",
        )

        expected = list(run.get("relation_scope") or [])
        relation_scopes = {
            item["relation_type"]: item
            for item in self.store.list_sync_run_scopes(sync_run_id)
            if item["collection_key"] == "__relation__"
        }
        terminal = {"complete", "partial", "failed"}
        all_terminal = bool(expected) and all(
            relation_scopes.get(relation, {}).get("status") in terminal
            for relation in expected
        )
        if not all_terminal:
            self.store.update_sync_run(
                sync_run_id,
                status="scanning",
                completeness="unknown",
                error_code=failure_code,
                error_message=(errors[0].get("message") if errors else None),
                evidence={
                    "waiting_for_relations": [
                        relation for relation in expected
                        if relation_scopes.get(relation, {}).get("status") not in terminal
                    ],
                    "closed_candidate_count": closed_candidates,
                },
            )
            return "scanning", closed_candidates

        all_complete = all(
            relation_scopes.get(relation, {}).get("completeness") == "complete"
            for relation in expected
        )
        final_status = "completed" if all_complete else "partial"
        self.store.update_sync_run(
            sync_run_id,
            status=final_status,
            completeness="complete" if all_complete else "partial",
            error_code=failure_code,
            error_message=(errors[0].get("message") if errors else None),
            evidence={
                "relation_scopes": relation_scopes,
                "closed_candidate_count": closed_candidates,
                "completed_at": utcnow(),
            },
        )
        if final_status == "completed":
            with self.store.connection() as con:
                con.execute(
                    "UPDATE source_account SET last_sync_at=?,updated_at=?,last_error_code=NULL WHERE id=?",
                    (utcnow(), utcnow(), account["id"]),
                )
        return final_status, closed_candidates

    def ingest_batch(self, sync_run_id: str, batch: SyncBatchRequest) -> dict[str, Any]:
        run = self.store.get_sync_run(sync_run_id)
        if not run:
            raise ValueError("同步运行不存在")
        # The browser worker observes controls between scopes, but a batch that
        # was already in flight can reach Core after the user pauses.  Core is
        # the final authority: do not let that late batch mutate the journal,
        # counters, checkpoints, or relation-closure evidence.  Resume moves
        # the run back to queued before the worker sends another batch.
        if run["status"] == "paused":
            raise ValueError("同步已暂停，请先继续后再提交批次")
        if run["status"] in {"cancelled", "completed"}:
            raise ValueError("当前同步运行不能再接收数据")
        account = self.store.get_source_account(run["source_account_id"], include_handle=True)
        if not account:
            raise ValueError("来源账号不存在")
        allowed = self._relations(account["platform"])
        if batch.relation_type not in allowed:
            raise ValueError("该关系类型不属于当前平台")

        self.store.update_sync_run(sync_run_id, status="normalizing")
        if batch.collection_name:
            # **服务端不替客户端猜这个 id。**（2026-08-07）
            #
            # 一度想在这里加「没给就退回 collection_key」的兜底，理由是生产上
            # `platform_collection` 三行的 `external_collection_id` 全是 NULL，
            # 分面那条 JOIN（`pc.external_collection_id = r.collection_key`）
            # 匹配 0 条，于是说明书答应的「收藏夹」筛选一直不出现。
            #
            # **量清楚之后没加**：那三行是 8/3–8/4 写的，而扩展在 v0.0.0.11
            # （8f32ef76）就已经显式发 `external_collection_id: group.key` 了，
            # 现在凡是发 collection_name 的批次都同时发它。兜底对真实客户端
            # 是死代码，却有真代价——**登记过的收藏夹才可能被判成「变空」**
            # （见 list_registered_collections），兜底会把登记范围放大，
            # 而他那 30 条挂在旧 key 下的收藏正是靠「没登记过」活着的。
            #
            # 真正要守的不变量在客户端那一侧：发名字就必须一起发 id。
            # 判据：test_the_collections_filter_can_actually_appear.py。
            self.store.upsert_platform_collection(
                source_account_id=account["id"],
                relation_type=batch.relation_type,
                name=batch.collection_name,
                external_collection_id=batch.external_collection_id,
                item_count=None,
                metadata={"sync_run_id": sync_run_id},
            )

        responses = []
        errors: list[dict[str, Any]] = []
        relation_ids_by_collection: dict[str, set[str]] = {}
        for index, item in enumerate(batch.items):
            if item.platform.lower() != account["platform"]:
                errors.append({"index": index, "code": "PLATFORM_MISMATCH", "message": "条目平台与来源账号不一致"})
                continue
            collection_key = batch.collection_key or item.collection_key or ""
            try:
                effective = item.model_copy(update={
                    "relation_type": batch.relation_type,
                    "collection_key": collection_key,
                    "source_account_id": account["external_account_id"],
                    "raw_metadata": {
                        **item.raw_metadata,
                        "sync_run_id": sync_run_id,
                        "batch_index": batch.batch_index,
                        "scope_type": batch.scope_type,
                    },
                })
                response = self.archive.capture(effective)
                responses.append(response)
                relation_ids_by_collection.setdefault(collection_key, set()).add(response.relation_id)
            except (ValueError, OSError) as exc:
                # 条目级错误：码要稳定，具体异常留在 message 里
                errors.append({"index": index, "code": "ITEM_INGEST_FAILED",
                               "message": f"{exc.__class__.__name__}: {exc}"[:500]})

        if relation_ids_by_collection:
            self.store.record_sync_seen_relations(
                sync_run_id=sync_run_id,
                relation_type=batch.relation_type,
                relation_ids_by_collection=relation_ids_by_collection,
            )

        receipt = {
            "completeness": batch.completeness,
            "item_count": len(batch.items),
            "cursor_end": batch.cursor,
            "failure_code": batch.failure_code,
            "scope": "account_relation" if batch.scope_type == "relation" else "account_collection_batch",
            "scope_type": batch.scope_type,
            "batch_index": batch.batch_index,
            "batch_count": batch.batch_count,
            "relation_type": batch.relation_type,
            "collection_key": batch.collection_key,
            "source_account_id": account["external_account_id"],
            "started_at": run.get("started_at") or utcnow(),
        }
        self.store.record_scan_receipt(
            account["platform"],
            f"{sync_run_id}:{batch.relation_type}:{batch.scope_type}:{batch.collection_key}:{batch.batch_index}:{len(run.get('events') or [])}",
            receipt,
            source_account_id=account["external_account_id"],
            relation_type=batch.relation_type,
        )

        # Every data batch updates counters and a resumable collection checkpoint.
        if batch.scope_type == "collection":
            collection_scope = batch.collection_key or "__mixed__"
            collection_complete = batch.completeness == "complete" and not batch.has_more and bool(batch.collection_key)
            self.store.upsert_sync_run_scope(
                sync_run_id=sync_run_id,
                relation_type=batch.relation_type,
                collection_key=collection_scope,
                status="complete" if collection_complete and not errors else ("partial" if errors else "scanning"),
                completeness="complete" if collection_complete and not errors else ("partial" if errors else "unknown"),
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
                failed_delta=len(errors),
            )
            closed_candidates = 0
            if collection_complete and not errors:
                observed = self.store.list_sync_seen_relation_ids(
                    sync_run_id=sync_run_id,
                    relation_type=batch.relation_type,
                    collection_key=batch.collection_key,
                )
                closed_candidates = self.store.apply_complete_scan(
                    account["platform"],
                    observed,
                    relation_type=batch.relation_type,
                    collection_key=batch.collection_key,
                    source_account_id=account["external_account_id"],
                )
            self.store.upsert_sync_checkpoint(
                source_account_id=account["id"],
                relation_type=batch.relation_type,
                collection_key=collection_scope,
                cursor=batch.cursor,
                known_anchor=batch.known_anchor,
                last_complete_sync_run_id=sync_run_id if collection_complete and not errors else None,
                complete=collection_complete and not errors,
            )
            self.store.update_sync_run(
                sync_run_id,
                status="scanning",
                completeness="unknown",
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
                failed_delta=len(errors),
                cursor={
                    "relation_type": batch.relation_type,
                    "collection_key": collection_scope,
                    "batch_index": batch.batch_index,
                    **batch.cursor,
                },
                error_code=batch.failure_code,
                error_message=(errors[0].get("message") if errors else None),
                evidence={
                    "waiting_for_relation_final": True,
                    "has_more": batch.has_more,
                    "closed_candidate_count": closed_candidates,
                },
            )
            next_status = "scanning"
        else:
            # **关系批次也要记数。**（2026-08-10）
            #
            # 之前只有 `scope_type == "collection"` 那一支加 discovered/imported，
            # 而**抖音/小红书/快手没有收藏夹分组，扩展送的就是 relation 批次**——
            # 于是那条路上计数一次都不加。真制品上实测：库里进了 1 条，
            # 而 run 报 `discovered 0 / imported 0 / duplicate 0 / failed 0`，
            # 他看到的是「同步完成，已导入 0 条」。**产品对他自己的数据说了假话。**
            self.store.update_sync_run(
                sync_run_id,
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
                failed_delta=len(errors),
            )
            next_status, closed_candidates = self._finalize_relation_scope(
                sync_run_id=sync_run_id,
                run=run,
                account=account,
                relation_type=batch.relation_type,
                completeness=batch.completeness,
                failure_code=batch.failure_code,
                errors=errors,
                discovered_delta=len(batch.items),
                imported_delta=len(responses),
            )

        return {
            "sync_run_id": sync_run_id,
            "status": next_status,
            "scope_type": batch.scope_type,
            "accepted": len(responses),
            "failed": len(errors),
            "content_ids": [item.content_id for item in responses],
            "errors": errors,
            "has_more": batch.has_more,
            "next_action_zh": (
                "继续后台同步。" if batch.scope_type == "collection"
                else ("本次账号同步完成。" if next_status == "completed" else "该关系已结束，继续处理其余关系。" if next_status == "scanning" else "同步部分完成，可从断点继续。")
            ),
        }
