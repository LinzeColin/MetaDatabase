# 六平台政策与能力门禁 — 2026-07-19 基线 / 2026-07-22 小红书当前页复核

本登记只回答“未来可以研究哪条合规路线”，不构成平台授权或法律意见。实现时必须重新核验当时的一手条款；任何未知都按 `UNKNOWN_DISABLED` 处理。

| 平台 | 一手能力证据 | v0.0.0.1 允许研究的首选路线 | 当前启用状态 |
|---|---|---|---|
| 小红书 | 官方分享开放平台当前公开资料仍以分享/发布能力为主；2026-07-22 复核仍未找到可验证的个人内容读取授权能力 | 已实现用户手势当前页 clean-room 解析，但本轮只允许公共安全合成 ID；真实页面与个人列表继续禁用 | `CI_SYNTH_ONLY / UNKNOWN_DISABLED_REAL` |
| 抖音 | 开放平台提供 OAuth/权限体系；用户视频等 Scope 需申请/授权 | 官方 API 优先；必要的当前页读取仅限用户选择、可见内容；禁止把第三方实现当授权 | `UNKNOWN_DISABLED` |
| 哔哩哔哩 | 开放平台提供用户授权/开放数据；开发者协议禁止未经书面同意用机器人/爬虫取得开放平台、用户或运营数据 | 官方 API 优先；当前页只读 fallback 必须通过独立 Gate | `UNKNOWN_DISABLED` |
| 快手 | 开放平台提供 OAuth、用户信息及内容能力，并要求明确同意与最小必要 | 官方 API/OAuth 优先；无 Scope 不启用个人列表 | `UNKNOWN_DISABLED` |
| 微博 | 官方开放平台/API/CLI 提供发布、互动、搜索等能力，当前配额/付费档位需独立预算决策 | 官方 API 优先；预算默认 0，未核验 Scope/成本前禁用 | `UNKNOWN_DISABLED` |
| 淘宝 | 淘宝开放平台提供 OAuth/API，Access Token 代表用户对私有信息授权；数据范围/留存受协议约束 | 官方 OAuth/API 优先；禁止 MTop Cookie 签名逆向作为基线 | `UNKNOWN_DISABLED` |

## 共同门禁

1. 只处理 Owner 明确选择的当前内容或明确选择的个人列表批次；搜索全网、用户画像、评论网络抓取不是 v0.0.0.1 产品范围。
2. 不自动滚动；分页也必须是用户明确动作定义的有界批次，且每批有最大条数、Deadline、Checkpoint 和可取消操作。
3. 不导出、接收、记录或持久化 Cookie/凭据；Browser Profile 由 Owner 管理，Secret 只进入系统 Keychain。
4. 不使用代理池、地域/频率规避、验证码绕过、设备/鼠标指纹伪装、未授权签名或账号状态变更。
5. 每个平台采用独立 Capability Manifest：`current_page`、`selected_collection`、`preview`、`ephemeral_download`、`classify`；状态只能是 `SUPPORTED`、`BLOCKED_POLICY`、`BLOCKED_AUTH`、`BLOCKED_TECHNICAL`、`UNKNOWN_DISABLED`。
6. “预览/下载”是 Local Companion 的临时媒体 Lease；成功后立即删除，失败最长 24h；数据库、日志、Markdown、Notion 和证据中平台 CDN URL 必须为 0。
7. 分类发生在 Canonical Content 上；平台适配器不能直接写 Markdown/Notion，AI 不能创建一级分类。

## 2026-07-22 小红书当前页复核结论

- `TSK.x2n.skeleton.001` 只证明合成 DOM、最小 Chrome 权限和本地链路；不构成平台授权或真实账号验收。
- 源码能力位固定为 `ci_synth_only`；非合成页面即使 URL 形态受支持也保持不可执行。
- 真实页面启用仍需当时的一手政策证据、Owner 明确授权、独立 Canary 和隐私披露复核；未知一律关闭。

## 一手参考

- Chrome Side Panel、Remote Hosted Code、Native Messaging 与 Chrome Web Store User Data/Limited Use：<https://developer.chrome.com/docs/extensions/reference/api/sidePanel>、<https://developer.chrome.com/docs/extensions/develop/migrate/remote-hosted-code>、<https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging>、<https://developer.chrome.com/docs/webstore/program-policies/user-data-faq>、<https://developer.chrome.com/docs/webstore/program-policies/limited-use>
- Notion request limits、capabilities、authorization 与 file upload：<https://developers.notion.com/reference/request-limits>、<https://developers.notion.com/reference/capabilities>、<https://developers.notion.com/guides/get-started/authorization>、<https://developers.notion.com/guides/data-apis/working-with-files-and-media>
- 抖音开放平台：<https://open.douyin.com/platform/resource/docs/operation-standard/agreement-protocol>、<https://open.douyin.com/platform/resource/docs/develop/permission/web/permission/>、<https://open.douyin.com/platform/resource/docs/accession-guide/type-and-permission>
- 小红书开放平台：<https://agora.xiaohongshu.com/doc>；协议页：<https://agree.xiaohongshu.com/h5/terms/ZXXY20230525001/-1>
- 哔哩哔哩开放平台与开发者协议：<https://openhome.bilibili.com/doc>、<https://openhome.bilibili.com/agreement/developer-service>
- 快手开放平台与协议：<https://open.kuaishou.com/platform/resourceCenter>、<https://open.kuaishou.com/platform/protocol>
- 微博开放平台：<https://open.weibo.com/cli/index>
- 淘宝开放平台与 OAuth：<https://developer.alibaba.com/docs/doc.htm?articleId=103499&docType=1&treeId=782>、<https://developer.alibaba.com/docs/doc.htm?articleId=120&docType=1&treeId=1>、<https://terms.alicdn.com/legal-agreement/terms/suit_bu1_other/suit_bu1_other201704191118_23239.html>
