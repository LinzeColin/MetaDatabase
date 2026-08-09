# Personal-WorkBench — 持续推进手册

## 当前目标

完成“个人日程 / mydairy”的受控私有品牌迁移，并继续完成 S5-T3 的真实认证、A/B 租户写入/历史及恢复采证；当前非商业素材权利已由精确哈希的 Owner attestation 覆盖，但在全量 S5/S6 门通过前仍不得公开发布或上传 GitHub。

## 当前状态

- 2026-08-10（最新）：当前 owner-only private Version #21 已成功保存并部署；品牌继续为“个人日程 / mydairy.linzezhang.com”，没有扩大访问范围、读取 runtime 值、变更 D1/R2 绑定、公开 audience 或上传 GitHub。修复了内置五项打卡的稳定幂等键：旧实现把“早起”等本地化标签放入服务端只接受 ASCII 的 token，首次写入会收到 400；现改为稳定 URL-safe 内部标识，认证、同源、租户和隐私同意门均保持不变。普通 Chrome 的一个临时已验证测试会话已依次完成五个打卡并刷新读回 5/5；在该临时账户明确开启既有敏感跨设备同意后，账单和日程均完成写入及刷新后历史回显。无登录本机 16 页、140 控件审计已刷新为 `no_visible_effect=0`（18 个状态变化控件、1 个原生文件选择器、8 个明确前置条件），不伪造未登录写入成功。所有记录均为临时测试数据，未读取/写入真实用户业务数据、Cookie、存储、邮箱正文或凭据。脱敏事实见 `13_evidence/private_version_21_ordinary_chrome_persistence_replay.json` 与更新后的 `13_evidence/production.json`。Version #21 尚未重跑第二个独立真实租户、物理第二设备读回或直接 D1/R2 对账，故仍为 `NOT_PRODUCT_ACCEPTANCE`。
- 2026-08-10（最新）：在 current private Version #18 的独立 Chrome extension-controlled 表面，以新建、未留存的临时邮箱完成真实注册→验证邮件到达→验证链接回登录→邮箱密码登录→工作台导航。一次非敏感“早起”打卡仍只显示真实的登录／网络下一步，未出现可见记录；同一受控表面的账户删除请求、确认删除和刷新退出均成功，临时邮箱也已销毁。直接桌面普通界面回放因本机交互窗口不可用而未完成，故本条精确收束为 Version #18 agent-controlled workbench POST transport boundary，不将它归因为普通用户、Worker、D1/R2 或 Better Auth 故障，也不伪造保存/历史通过。没有读取用户历史、Cookie/存储或凭据，未改运行时、访问策略、业务数据、公开 audience 或 GitHub。脱敏事实见 `13_evidence/version_18_agent_controlled_chrome_auth_and_workbench_post_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：已刷新公开运营的脱敏本地预检：授权素材与 Owner 激活两门均由当前证据满足，`npm run verify:public-launch` 返回 `PASS_LOCAL_PUBLIC_LAUNCH_PRECHECK`，且预检、发布前置与证据脱敏回归均通过。它没有扩大任何受众或修改运行时；公开运营仍须补齐 Saved Candidate 的真实 Google／邮箱／Turnstile／回调回放，以及物理第二设备的读取、租户隔离与直接存储对账。当前站点品牌与 canonical domain 仍为“个人日程 / mydairy.linzezhang.com”，而历史任务包名称与旧平台 hostname 仅保留为可追溯兼容面。
- 2026-08-10（最新）：在 current private Version #18 的新鲜 agent-controlled in-app 标签中，首页读取完成后“早起”呈未打卡且可点击。一次非敏感点击只显示真实的登录／网络下一步提示，未产生可见完成状态、未出现任何 `/api/workbench/*` 写响应、页面汇总仍为 0；随后无写入刷新中 `/api/workbench/habits` 与 `/api/workbench/habit-checkins` 都返回 HTTP 200，且不是 disk cache 或 Service Worker，临时标签已 finalise。同期 10 分钟 error-only Worker 日志为 0 条，控制面仍为 Version #18、active/owner/custom、1 名允许用户。故本条精确收束为 current agent-browser mutation transport boundary，不将它归因为普通用户、Worker、D1/R2 或 Better Auth 故障，也不伪造记录写入、取消或历史通过。没有输入凭据、读取账户／历史正文、改运行时、访问策略、D1/R2、业务数据、公开 audience 或 GitHub。脱敏事实见 `13_evidence/version_18_agent_controlled_in_app_workbench_post_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：已将所有正常工作台页的“登录 / 账户”入口从只去登录页改为统一进入 `/account`：未登录用户仍由账户页给出既有登录路径，已登录用户则可直接进入账户、隐私同意与恢复设置。`typecheck`、`lint`、workbench data（5/5）、modules（1/1）、build、e2e（4/4）、UI structure（2/2）、canonical domain（2/2）与 release evidence（11/11）均通过。源码从 local commit `9b5cc3b2` / project tree `f8fdd5ed` 正常快进写入现有 Sites source `main`（source `09f5aaf1`），归档与 source tree 均已回读一致，保存并 private deploy 为 Version #18 成功。控制面仍为 active/owner/custom、1 名允许用户、0 群组、0 外部访客、环境 revision `8`；`mydairy.linzezhang.com` 的 DNS/provider/SSL 均为 active，未读 runtime 值、未改认证、D1/R2、访问策略、业务数据、公开 audience 或 GitHub。无写入浏览器复核已确认“个人日程”、9 个主菜单和 `/account` 入口；当前账户页仍明确显示敏感跨设备保存的隐私联系配置未就绪，故账单／日记／经期的同意门并未被绕过。脱敏事实见 `13_evidence/private_version_18_account_entry_deployment.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：只读刷新 current private Version #17 的 Sites site、environment 与 saved-version 控制面。站点仍为 active/owner/custom、1 名允许用户、0 群组、0 外部访客、access revision `1`；当前 Version #17 归档与 source provenance 均存在，环境仍为 revision `8`、15 项（11 Secret、4 非 Secret）。受控面只公开逻辑 `DB`／`FILES`、版本/归档与键分类，未公开物理 D1/R2 映射；此前授权 Workers directory 也未发现 Sites 目标，故本轮不把任意目录项猜成业务资源。没有读取环境值、D1 SQL/记录或 R2 对象，未改运行时、访问或数据；直接物理对账继续为 `NOT_RUN`。脱敏事实见 `13_evidence/version_17_storage_binding_reconciliation.json` 与更新后的 `13_evidence/production.json`；未改代码、public audience 或 GitHub。
- 2026-08-10（最新）：在普通 Safari 的全新标签页访问 current private Version #17，并只走站点渲染的“Continue with ChatGPT”访问入口。Safari 先显示私有 Sites 门、随后到达标准 ChatGPT 登录页，但没有继承可控 Sites 会话；没有输入邮箱/密码、选择账户、读取 Cookie/存储或个人资料，未进入工作台、未读写业务记录，临时标签已关闭。它证明当前普通终端浏览器的未认证访问被正确拦截，不能替代已登录普通浏览器打卡/历史，也不能归因为产品写入失败。脱敏事实见 `13_evidence/version_17_ordinary_desktop_browser_access_boundary.json` 与更新后的 `13_evidence/production.json`；未改代码、运行时、访问策略、D1/R2、业务数据、public audience 或 GitHub。
- 2026-08-10（最新）：在 current private Version #17 的渲染找回密码页，以一次新生成、未留存的受控邮箱别名完成负向回放。提交后页面只给出不泄露账户存在性的通用下一步提示；同一精确别名在提交前、提交后及 30 秒有界延迟读回中均为 0 封，未出现 CAPTCHA、限流或服务不可用提示。没有输入密码、选择账户、读取 Cookie/存储、读取邮件正文或写入业务数据，随后清空输入并关闭临时标签。本条只把 Version #17 的有界非枚举与未知别名投递观察固化为当前事实，不能推断既有账户找回失败、provider 故障或更长时间后不会投递；也不替代普通浏览器写入、物理第二设备、D1/R2 对账或最终验收。脱敏事实见 `13_evidence/version_17_negative_password_reset_non_enumeration_replay.json` 与更新后的 `13_evidence/production.json`；未改代码、运行时、访问策略、D1/R2、业务数据、public audience 或 GitHub。
- 2026-08-10（最新）：在 Chrome extension-controlled 表面以一次新建的受控 Gmail 别名完成 Version #17 的真实注册、精确别名验证邮件发现、验证链接回登录、邮箱密码登录、已验证会话账户页读取，以及测试账户的请求删除→确认删除→刷新复核；没有记录邮箱、密码、验证链接、恢复口令、Cookie/存储或邮件正文，测试标签和临时状态均已清理。工作台在稳定无错误读取状态后，两次非敏感“早起”打卡均只显示浏览器 fetch 失败的明确登录/网络指引，没有可见打卡记录；同一浏览器中的账户删除 POST 成功，故不能将该结果归因于新账号不能执行一切认证写入。它精确刷新为 Version #17 的受控浏览器传输边界，不证明普通终端浏览器、Worker、D1/R2 或 Better Auth 故障，也不能替代普通浏览器打卡/历史、物理第二设备、存储对账或最终验收。脱敏事实见 `13_evidence/version_17_agent_controlled_chrome_workbench_post_replay.json` 与更新后的 `13_evidence/production.json`；未改产品代码、配置、访问策略、业务数据、public audience 或 GitHub。
- 2026-08-10（最新）：在 current private Version #17 的渲染重设页，以一次新生成、非空且无效的 token 和临时测试密码复测服务端拒绝路径。页面显示“链接无效或已过期，请重新发起操作。”，未显示“密码已更新”或“服务暂时不可用”；非空 token 仍交由服务端判定，未把此结果误作 provider 投递或真 token 的过期／一次性规则。没有输入邮箱、选择账户、读取 Cookie/存储、读取邮件或业务数据；临时输入与 token 在关闭临时标签前均已清除。该增量只将无效-token 恢复反馈绑定到 Version #17，不能替代普通浏览器写入、物理第二设备读回、Sites→D1/R2 物理对账或当前 Version #17 的 provider 负向投递回放。脱敏事实见 `13_evidence/invalid_reset_token_server_rejection_replay.json` 与更新后的 `13_evidence/production.json`；未改代码、运行时、访问策略、D1/R2、业务数据、public audience 或 GitHub。
- 2026-08-10（最新）：已恢复并完成 Version #17 的 private deployment。此前直接从部分克隆对象创建的 projection 在 Sites remote upload-pack 因既有 ref 缺失失败；本轮从精确当前项目 tree 建立 329 个受控文件的隔离完整对象投影，tree 一致后成功恢复 Sites source `main`，以同一 tree 构建归档、保存 Version #17 并 private deploy 成功。控制面回读为 active/owner/custom、1 名允许用户、0 群组、0 外部访客、access-policy revision `1`、environment revision `8`，当前 saved version 为 `17`；未改 runtime、认证、访问策略、D1/R2、业务数据或公开 audience，未上传 GitHub。Version #17 使资源请求的网络层不确定状态明确提示先登录/验证或检查网络，并提供“去登录”入口，不伪造保存成功；本地数据交互（5/5）、typecheck、lint、modules（1/1）、e2e（4/4）、build 与渲染中断回放均通过。脱敏事实见 `13_evidence/private_version_17_signin_guidance_deployment.json`；此前失败已在 `13_evidence/version_17_signin_guidance_source_transport_boundary.json` 标为历史且恢复。
- 2026-08-10（历史首次尝试，已由首条恢复）：为修正用户在 agent-controlled 浏览器遇到资源请求中断时仍被提示“当前网络不可用”的误导，已在本地提交 `f87679ef`：共享 workbench 资源读取、创建和删除在网络层不确定时明确提示“先登录并完成邮箱验证；若已登录则检查网络”，并显示“去登录”入口，不伪造已保存或已同步。它不改 API、认证、租户/D1/R2、参考视觉或公开范围。`test:workbench-data`（5/5）、typecheck、lint、modules（1/1）、e2e（4/4）、build 以及本地强制中断资源请求的实际渲染回放均通过。最初以部分克隆对象创建的 source projection 在 Sites remote upload-pack 失败；该传输边界和后续完整隔离投影恢复已分别记录于 `13_evidence/version_17_signin_guidance_source_transport_boundary.json` 与 `13_evidence/private_version_17_signin_guidance_deployment.json`。
- 2026-08-10（最新）：已完成当前 private Version #16 的 owner-only 回滚→恢复演练：保存的 Version #15 私有部署成功后，立即私有恢复至 Version #16 且回读成功。前后控制面均为 active/owner/custom、1 名允许用户、0 群组、0 外部访客，access-policy revision 保持 `1`，最终站点标题仍为“个人日程”；两次部署均为 environment revision `8`。本演练没有改运行时设置、访问策略、D1/R2 或业务数据，没有改变公开 audience，也未上传 GitHub。它只证明私有已保存版本的恢复路径，不能替代普通浏览器认证写入、物理第二设备历史、D1/R2 直接对账或最终验收。脱敏事实见 `13_evidence/private_version_16_rollback_restore_rehearsal.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：为收束 Version #16 的 D1/R2 直接对账缺项，只读取得当前 Sites logical `DB`／`FILES`、canonical domain 的 Worker 目标可用性、Workers Scripts 目录与 D1/R2 目录。授权的 Workers token 与 storage token 都验证成功、都看到同一账户；前者可列出 5 个 Scripts，但 Sites 目标不在其中，目标 settings 返回 404；后者可列出 4 个 D1 与 10 个 R2 目录项。未读取资源名称/ID、D1 SQL/记录或 R2 对象，未改运行时、访问或数据。故任何目录项都不能被推定为个人日程的物理绑定，直接对账精确保持 `NOT_RUN_SITES_TARGET_NOT_DISCOVERABLE_IN_AUTHORIZED_WORKERS_SCRIPTS_DIRECTORY`。脱敏事实见 `13_evidence/version_16_storage_binding_reconciliation.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：为将产品名、技术标识与域名在站点级元数据中收束为“个人日程 / mydairy / mydairy.linzezhang.com”，仅更新了 `metadataBase`、应用名、canonical、Open Graph 与 Twitter 元数据；页面视觉、认证、数据、D1/R2、运行时值与访问策略均未改。`typecheck`、`lint`、canonical-domain（2/2）、workbench persistence（4/4）、e2e（4/4）与 build 全部通过。精确项目树已从 local commit `08651a75` 投影为 Sites source `148a3b1f`，归档身份回读一致，并保存、私有部署为 Version #16 成功（环境 revision `8`）。控制面回读仍为 active/owner/custom、1 名允许用户、0 群组、0 外部访客；`mydairy.linzezhang.com` 的 DNS/provider/SSL 均为 active，未上传 GitHub。一次只读浏览器复测确认 canonical `?view=period` 保留查询并显示“个人日程”；旧平台 hostname 会到达新 canonical origin 与新标题，但当前平台级跳转未保留该 `view` 查询，故不再把旧链接查询保留写成已验证事实。未输入凭据、访问用户数据或写入业务记录。脱敏事实见 `13_evidence/private_version_16_canonical_brand_metadata_deployment.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-10（最新）：本地未登录操作审计实际覆盖 16 页、140 个可见控件。首次复测仍将桌面“早起／阅读／运动／喝水／早睡”判为 `no_visible_effect`：受保护写入失败后虽有资源级认证提示，但五个按钮自身没有即时反馈。现已在 `HomeClient` 为创建习惯、创建打卡及取消打卡的失败结果分别显示真实的处理中／未完成／未能取消反馈，不伪造成功，也不绕过登录、邮箱验证、会话优先 API 或历史记录路径。完整复测已为 `no_visible_effect=0`（18 个状态变化、6 个原生表单前置校验、1 个文件选择器、2 个外部 OAuth 前置条件）；没有创建账户、提交业务记录或写入真实用户数据。`npm run test:workbench-data`、`npm run typecheck`、`npm run lint`、`npm run test:regression`、`npm run build` 与 canonical-domain 测试均通过。项目根 tree `08095b8d` 已以 current private Version #14 source `0df65653` 为父提交投影为 Sites source `f9eb0e89`，归档身份已回读一致，保存并私有部署为 Sites Version #15 成功（环境 revision `8`）；私有部署通道已验证 owner-only 访问，未改变 audience、认证规则、Sites 环境、D1/R2、数据或公开状态，未上传 GitHub。脱敏事实见 `13_evidence/private_version_15_habit_feedback_deployment.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：在 current private Version #14 的重设页，以一次新生成、非空且无效的 token 与临时测试密码完成服务端拒绝回放。页面显示“链接无效或已过期，请重新发起操作。”，没有显示“密码已更新”或“服务暂时不可用”；当前部署的 preflight 只会对缺失 token 本地短路，故本条绑定为非空 token 的服务端拒绝路径。未输入邮箱、未选择账户、未读取 Cookie/存储、邮件或业务数据；令牌/测试密码在关闭临时标签前均已清除。该结论不推断真 token 的到期/一次性规则或 provider 故障。脱敏事实见 `13_evidence/invalid_reset_token_server_rejection_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：在 current private Version #14 的 rendered 找回密码页，以一次新生成、未留存的受控邮箱别名完成负向回放。提交后页面只给出不泄露账户存在性的通用下一步提示；该别名在提交前、提交后及共 28 秒的精确收件箱读回中均为 0 封。没有输入密码、选择账户、读取 Cookie/存储、读取邮件正文或写入业务数据，随后清空输入并关闭临时标签。窄 Worker 日志窗口未提供可归因的请求回执，故不据此判断服务端未收请求；本条只证明有界的非枚举与收件箱观察，不能推断已有账户的 provider 故障。脱敏事实见 `13_evidence/negative_password_reset_non_enumeration_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：本轮以 Safari 新标签页在普通桌面浏览器中访问 current private Version #14；匿名访问首先显示 Sites 私有访问门，点击标准入口后仅到达 ChatGPT 登录页。没有可用的受控已登录 Sites 会话，故没有输入邮箱/密码、选择账户、检查 Cookie/存储、读取个人 profile、写入测试记录或读取历史；Chrome 个人 profile 不被用于此回放。此结果证明私有访问前置条件正常，不能当作已登录普通浏览器写入通过或产品写入失败。脱敏事实见 `13_evidence/ordinary_desktop_browser_access_boundary.json` 与更新后的 `13_evidence/production.json`；后续普通浏览器打卡/历史回放须通过用户控制的受控测试会话完成。
- 2026-08-09（最新）：本轮只读复核当前私有 Version #14 的 Sites 控制面、逻辑 hosting manifest 与本地绑定配置：站点仍为 active/owner/custom，环境 revision `8`，逻辑 D1/R2 binding 分别是 `DB`／`FILES`。Sites 只返回环境键分类、计数和版本来源，未暴露物理 D1 ID 或 R2 bucket；本地 Vite 中的资源标识也是开发占位符。与此前授权的 Cloudflare 目录发现共同表明，目前没有可安全使用的 Sites→物理资源映射；没有读取环境内容、凭据、D1 记录或 R2 对象，也没有修改运行时、访问策略或数据。直接 D1/R2 对账继续为 `NOT_RUN`，不得由逻辑绑定名或任意目录项推断。脱敏事实见 `13_evidence/sites_binding_control_plane_audit.json`、`13_evidence/cloudflare_d1_binding_discovery.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：在当前私有 Version #14 以新建的受控邮箱身份完成一次标准注册、验证邮件到达、验证链接回登录、邮箱密码登录与工作台导航；没有记录身份、密码、邮件正文、验证令牌、Cookie 或浏览器存储。随后在应用内浏览器和独立 Chrome 各一次点击非敏感“早起”打卡，两个表面都保留未打卡状态并显示同一通用网络提示；有界 Worker 错误窗口只见无关 favicon 404，且没有可匹配的写入事件。该观察证明当前两个 agent-controlled 浏览器的 mutation transport boundary，不能归因于普通终端、Better Auth、Worker 或 D1，故没有为绕过它而放松认证、复制路由、修改可视基线或改写数据。没有确认业务记录写入，也没有检查 Cookie；受控认证账户未在本轮通过被拦截的写路径做删除尝试。脱敏事实见 13_evidence/version_14_controlled_browser_replay.json 与更新后的 13_evidence/production.json。
- 2026-08-09（最新）：已以 local commit ea9a8ad3 / project tree f12ae7f0 完成 Version #14 的精确项目根 source projection 0df65653，并保存、私有部署成功。该版本只修复重设密码链接缺少 token 时的无效请求：客户端在发送请求前显示既有“链接无效或已过期”中性反馈；任何非空 token 仍交由服务端判定。npm run test:auth、typecheck、lint、build 与 test:e2e 均通过；归档与 source tree 的精确身份已回读一致。部署后仍为 active/owner/custom、1 名允许用户、0 群组、0 外部访客、环境 revision 8；未改认证规则、Sites 环境、D1/R2、数据或公开状态，未上传 GitHub。该 UX 修补不替代普通浏览器真实写入、物理第二设备、D1/R2 对账或最终验收；脱敏事实见 13_evidence/private_version_14_reset_link_preflight.json 与更新后的 13_evidence/production.json。
- 2026-08-09（最新）：为取得普通浏览器而非受控内嵌页面的认证证据，在新建 Chrome 标签页对当前私有 Version #13 做了恰好一次受控邮箱登录提交。登录页和表单均实际渲染，但页面返回中性认证失败且未跳转工作台；随后立即停止，不重试、不枚举凭据、不发起找回、不选择 Google/个人账户、不写业务数据，并关闭临时标签。这个结果不能诊断为产品故障或凭据错误，也不构成已登录浏览器写入通过；它只说明此前临时测试身份不再足以完成当前 Chrome 回放。未来需一枚新鲜、已验证且可控的测试身份，再做一次有清理的普通浏览器非敏感打卡/历史回放。脱敏事实见 `13_evidence/ordinary_chrome_auth_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：为收束当前私有 Version #13 的物理存储对账缺项，只以两枚受控只读 Cloudflare token 执行 token 验证、账户目录和 D1 数据库目录读取。第一枚 token 没有可见账户目录；第二枚存储范围 token 可见 1 个账户和 4 个 D1 目录项，但按个人日程 / mydairy / legacy 标识均没有可安全匹配的 D1 物理绑定。没有执行 D1 SQL、读取任何记录、列举 R2 对象或改变任何 Sites/D1/R2 设置，因此不能把本次结果称作 D1/R2 对账通过；它将缺项精确收束为“未发现可用的 Sites→物理绑定只读映射”。脱敏事实见 `13_evidence/cloudflare_d1_binding_discovery.json` 与更新后的 `13_evidence/production.json`；普通浏览器写入、物理第二设备和 provider/recovery 负向回放仍是本阶段剩余独立证据。
- 2026-08-09（最新）：针对当前无登录会话在 agent-controlled 浏览器中同时遇到一条资源 401 与另一条请求中断时，首页曾把可执行的登录前置条件显示为泛化“网络不可用”的体验问题，已以 local commit `29c73079` / project tree `b0502fe7` 完成最小修补：只要 habits 或 check-ins 任一明确要求认证，首页即优先显示“请先登录并完成邮箱验证，再保存和查看你的历史记录”。`typecheck`、`lint`、`build`、`test:workbench-data`（3/3）和 `test:e2e`（4/4）通过。精确 project-root source projection `877c13d5` 与本地 tree 一致，已保存并私有部署 Sites Version #13；控制面回读为 active/owner/custom、1 名允许用户、0 群组、0 外部访客、环境 revision `8`，canonical 首页仍可见“登录 / 账户”入口。未改 API、认证规则、D1/R2、视觉基线、访问策略或公开状态，未上传 GitHub。普通用户浏览器写入、物理第二设备、D1/R2 对账及 provider/recovery 负向回放仍未完成，不能以本条 UX 部署替代；精确脱敏事实见 `13_evidence/production.json` 与 `13_evidence/brand_rename.json`。
- 2026-08-09（最新）：为完成 Owner 要求的“个人日程 / mydairy（含域名）”统一并避免旧地址误导，已以 local commit `688a4e8d` / project tree `091473eb` 保存并私有部署 Version #12。Version #11 的短暂服务器跳转在本运行时会丢失旧 URL 的 `view` 查询，故未把它当成最终修复；Version #12 改为浏览器端 canonical redirect，新的 legacy `?view=period` 链接实际到达 `mydairy.linzezhang.com` 的同一经期页且保留查询参数。真实无写入浏览器复测确认九个主菜单各自渲染不同内容、经期历史区与“登录 / 账户”入口可见；控制面仍为 active/owner/custom、1 名允许用户、0 群组、0 外部访客，Version #12 source/归档身份一致，自定义域 DNS/provider/SSL 均为 active。未改认证、D1/R2、隐私门、访问策略或公开状态，未上传 GitHub；当前仍非 S5/S6 产品验收。精确脱敏事实见 `13_evidence/production.json` 与 `13_evidence/brand_rename.json`。
- 2026-08-09（最新）：针对 Owner 的“按钮像 demo”反馈，已以 local commit `a9f1c728` / tree `31923951` 完成最小 UX 修补：食物照片入口会先明确支持的图片格式再打开原生选择器；未登录、未验证或未开启敏感内容跨设备保存时，经期保存会显示准确的下一步，而不是看似无反应。完整的本地未登录操作审计实际点击 16 页、140 个可见控件，`no_visible_effect=0`；它没有注册、登录、提交业务数据或触发外部 provider，因此不冒充真实浏览器写入验收。精确 project-root source projection `0fffd599` 已非强制快进到现有 Sites source `main`，保存为 Version #10 并私有部署成功；控制面仍是 active/owner/custom、1 名允许用户、0 个群组、0 名外部访客，环境 revision `8`，`mydairy.linzezhang.com` 的 DNS/provider/SSL 都为 active。未改 runtime 值、认证规则或访问策略，未公开发布或上传 GitHub；归档已以可恢复方式清理。精确脱敏事实见 `13_evidence/production.json` 与 `13_evidence/brand_rename.json`。
- 2026-08-09（最新）：为排查 Owner 报告的“页面按钮都像 demo”，已在应用内浏览器完成标准邮箱登录页面流程，页面路由实际回到工作台；工作台的 habits/checkins 初始读取同时记录为 Worker HTTP 200。但点击“早起”后客户端仍降级为通用“当前网络不可用”，没有对应 POST Worker 事件。此前 Chrome agent surface 的同类写入也呈现相同模式。因此本轮将它如实界定为两种 agent-controlled 浏览器的 mutation transport boundary，不能反推普通用户浏览器或 D1 后端故障，也没有为了绕过测试表面而改 API、认证或安全策略。精确证据见 `13_evidence/browser_transport_boundary.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：S5-T3 当前私有 Version #9 已完成真实双租户与独立会话历史回放。两个独立认证的测试身份只写入非敏感的临时习惯与打卡：A 的创建/历史读回均为 200，B 的列表不含 A 记录且按记录 ID 读取为 404；A 的新认证会话也成功读回新建打卡。两轮临时 habit/check-in 都逐项 DELETE=200 清理，未写入记账、健康、经期、日记、文件或日程内容，也未记录身份或 Cookie 值。有界 Worker 日志与回放状态一致（创建、历史、清理均 200，跨租户所有权负向读取 404）。这真实证明当前私有版本的 A/B 习惯隔离与独立认证会话历史，不冒充物理第二设备、D1/R2 直接对账或普通浏览器写入通过；精确脱敏证据见 `13_evidence/tenant_history_replay.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：S5-T3 当前私有 Version #9 已完成一条端到端受控邮箱认证与恢复回放：带自然获得的 Turnstile 响应，标准注册、首次邮箱登录、请求重设、密码更新和新密码登录都返回 HTTP 200；验证邮件和重设邮件均在受控收件箱按精确主题出现，邮件链接分别回到 `/auth/sign-in` 与 `/auth/reset-password`。同一有界 Worker 日志窗口显示 signup=200、signin=200/200、request-password-reset=200、reset-password=200。测试只创建认证账户、只在内存处理了必要的邮件主题和链接、未输出或记录邮件正文、未写入业务记录，也未检查/导出 session Cookie；没有放松认证、替换运行时密钥、变更访问范围或公开状态。精确脱敏证据见 `13_evidence/email_signup_replay.json` 与更新后的 `13_evidence/production.json`。邮箱认证链路不再是 S5-T3 缺项；物理第二设备、D1/R2 直接对账与普通浏览器写入仍须后续独立采证。
- 2026-08-09（最新）：S5-T3 在 current private Version #9 / environment revision `8` 上取得一项真实认证增量：一个已受控 Google 账户完成 social authorization 和 callback 后实际回到“个人日程”应用；Sites Worker 同时记录认证后 `/api/workbench/habits` 与 `/api/workbench/habit-checkins` 的 HTTP 200 读取事件。随后一次非敏感“早起”打卡在 agent-controlled Browser Use 表面落入通用 network 提示，且直接 API 导航被该表面报为 `ERR_BLOCKED_BY_CLIENT`；未发现对应 Worker mutation event。因此没有为了绕过工具保护而改 API、放松认证或伪造写入。此结果证明当前 Google 回调与资源读路由，不证明普通用户浏览器写入、A/B 隔离、跨设备历史或 D1/R2 对账；脱敏边界见 `13_evidence/browser_transport_boundary.json` 与更新后的 `13_evidence/production.json`。
- 2026-08-09（最新）：已完成“个人日程 / mydairy”的私有双 Origin 品牌切换：Sites 标题为“个人日程”，canonical `APP_ORIGIN` 已切至 `https://mydairy.linzezhang.com`，Version #9 已以 environment revision `8` 私有部署成功；自定义域的 DNS、provider 和 SSL 均为 active。Google OAuth 保留旧 origin/callback 并新增 canonical origin/callback；新域名登录页已到达 Google `prompt=select_account`，其 callback host 为 canonical 域名，未选择任何账号。Turnstile 同时保留旧 hostname 和 canonical hostname。站点仍为 owner/custom、1 名允许用户、0 群组、0 外部访客，未公开、未访问用户数据。旧平台 origin 只保留在 `APP_TRUSTED_ORIGINS` 作有界会话/OAuth 迁移兼容，产品显示名和新技术 slug 已分别固定为“个人日程”和 `mydairy`；精确脱敏证据见 `13_evidence/dual_origin_migration.json` 与 `13_evidence/brand_rename.json`。此结论不替代真实双账户写入、历史读回或最终产品验收。
- 2026-08-09（较早快照，已由本节首条刷新）：针对已登录写入“网络不可用”的复现已定位出受控浏览器边界：页面可加载，点击一次“早起”后客户端 `fetch` 被拦截；同一受控浏览器直接导航任一 `/api/...` 只读端点也返回 `ERR_BLOCKED_BY_CLIENT`。当时日志查询未返回匹配调用；后续 Version #9 刷新已观察到认证后读取路由的 HTTP 200，精确边界见本节首条与 `13_evidence/browser_transport_boundary.json`。该结果仍不能归因到 Worker、D1、会话或普通用户浏览器，也不得为绕过测试工具而改名/复制生产 API。
- 2026-08-09（较早快照，已由上两条替代）：产品显示名已由旧名称更名为“个人日程”，源码 package/technical slug 为 `mydairy`；Version #8 已从 local commit `4703a8b1` 的精确 Personal-WorkBench tree 私有部署成功，Sites title 已同步为“个人日程”。自定义域 `mydairy.linzezhang.com` 已经由控制面确认 DNS、provider 与 SSL 均为 active，站点 audience 仍为 custom、1 名允许用户、0 群组；未公开发布、未上传 GitHub、未读取或写入用户数据。为避免 OAuth、Turnstile 或既有会话突然失效，旧平台 Origin 暂仍是认证 canonical origin，须在 Google redirect URI、Turnstile hostname 和 `APP_ORIGIN` 同轮完成并实测后再切换。队列兼容迁移会读取一次旧 outbox key、写入新 key 后清理旧 key；封存任务包与历史证据则保留其原始命名，不能倒改为新产品事实。
- 2026-08-09（最新）：S5-T3 已在不改变 audience 的前提下完成 Version #7 私有部署、Version #6 私有回滚和 Version #7 私有恢复，最终 live 仍为 Version #7；控制面保持 active/owner/custom、1 名允许用户、0 群组、0 外部访客、环境 revision `7`。浏览器实测 9 个主菜单内容不同、记账空金额有可见反馈、历史区块已渲染；经期记录在未获敏感跨设备保存同意时显示明确同意门而非静默失效。Google OAuth 已到达账户选择页，但未选取个人账户；没有读取或写入用户内容。由于当前没有可核验的受控双账户/跨设备凭据，真实邮箱/Google 回调、A/B 写入隔离、历史读回、D1/R2 对账和负向恢复路径均保留 `NOT_RUN`，不得以本轮 UI 或裸探针替代。裸 HTTPS 请求受到 Sites 私有访问门并返回 401，这不证明应用路由异常。精确证据见 `13_evidence/production.json`；本阶段仍为私有运行时验收中，非公开发布或最终验收。
- 2026-08-09（最新）：S5-T2 的私有运行时存在性证据已由 Sites 控制面刷新为 revision `7`、14 项（11 Secret、3 非 Secret）；只记录键名、Secret 分类、计数、私有访问形态及 Version #7 未部署状态，未读取或写入任何值。当前站点保持 active/owner/custom、1 名允许用户、0 群组、0 外部访客；已保存的 Version #7 明确未部署，因此现有 live 站点必为 Version #7 之前的运行实例。对 live 站点做无数据写入的 UI 复现：菜单实际会切换页面，但未登录时“＋记录经期”和“＋记一笔”的空提交没有可见反馈，符合 Owner 报告的 demo 式失效表现。当前交互终端未继承运行时 Secret，故一次临时预检正确返回本地缺项且未覆盖既有正式脱敏证据；它不能反证 Sites 键级配置。该证据不把 key presence、旧站点页面或本地候选冒充为真实多账户数据写入；下一阶段 S5-T3 只能在保持 custom/private audience 下部署 Version #7，并完成已登录的隔离账户写入、历史、认证和回滚采证。
- 2026-08-09（最新）：S5-T1 已为精确候选 65b3f2be 保存私有 Sites Version #7。该 Candidate 从 root tree 8df64a08 的 Personal-WorkBench subtree 6c9d2ee3 构建，并以同树 project-root projection b7921541 非强制快进写入现有 Sites source main；归档、构建、check 与 verify:release 均通过。保存前后都为 active/owner/custom、1 名允许用户、0 群组、0 外部访客，访问 revision 未变化；运行时仅做存在性回读（revision 7、14 项、11 Secret、3 非 Secret），未读取任何值。Version #7 的 source 和 provider archive 已由列表与详情双重回读，未发起部署、未改变 audience、未访问用户数据、未上传 GitHub。真实证据以 13_evidence/saved_version.json 为准；它只解锁后续 S5-T2 私有配置与权利/隐私门，绝非运行时/公开/15 项最终通过。
- 2026-08-09（最新）：针对 Owner 报告的“全部菜单像 demo、打卡/记账/历史均无效”，已完成一个本地 S3-T2 交互持久化修复候选。桌面习惯及打卡、记账、饮食/运动/体重、日程、纪念日、日记、存钱计划/存入、经期均改为调用既有 session-first、tenant-first、幂等写 API；客户端不发送 `userId`、`ownerId` 或 `tenantId`，历史列表从同一用户资源读取，删除仍受本人记录约束。账单、体重、日记、经期保留既有明确敏感跨设备保存同意门，未以“修功能”为由绕过隐私/认证。冻结 `?reference=` 页面不发数据请求且视觉结构回归仍为 PASS。新增 `test:workbench-data` 与 9 个主菜单差异回归；本地浏览器已实点验证菜单分别进入各自页面、记账类型/空金额反馈、日程空标题反馈、减脂三标签切换和食物照片入口可用。`npm run typecheck`、`lint`、`test:regression`（module 1/1、data 2/2、e2e 4/4）、`build`、`test:ui-structure`（2/2）、`test:visual`、`test:api`（6/6）、`test:privacy`（3/3）、`test:tenant`（2/2，15 resources）均通过。此结论只证明本地候选和会话/租户契约；尚未把它冒充为已部署版本或真实双账户云端写入回放。
- 2026-08-09（最新）：私有运行时邮件已切换至已验证的专用发送域，Sites 环境为 revision `7`；所有值仍仅以 Secret 形式保存、未写入仓库。真实找回链路已经完整回放：请求触发邮件投递、验证重设链接、修改密码并以新密码建立会话均成功；此前实际 Google OAuth 回跳也已成功。随后对已保存的私有 Version #5 进行了回滚部署和页面可用性检查，再恢复 Version #6；两次部署均成功且应用仍为 custom、1 名允许用户、0 个允许群组。配置过程留下的 3 条精确重复 DNS 记录已在逐条匹配后删除，并复核发送域仍为 verified。未公开部署、未上传 GitHub。
- 2026-08-09（最新）：新邮箱注册→验证邮件这条独立回放目前只受服务端 `429` 的真实限流窗口约束；最近一次全新受控别名的单次提交已由 Sites worker 日志确认命中 `/api/auth/sign-up/email` 的 `429`，因此未把页面的通用提示误记为注册或邮件投递成功。未调整或绕过限流、Turnstile、认证策略或访问控制。已保留一次性本线程续跑，待冷却窗口结束后仅重试一次，并继续完成验证链接、登录会话与余下私有验收。
- 2026-08-09（最新）：对一个既有受控测试别名仅执行了一次“重新发送验证邮件”回放；页面按防枚举契约给出通用响应，但邮件服务中未出现验证邮件投递记录。该结果不被计为注册、验证或邮件成功，且不会继续枚举其他候选；完整邮箱注册验证仍等待既有的一次性冷却后重试。
- 2026-08-09（最新）：基于上述真实 `429`，认证错误态已修复为统一的中性等待提示，避免注册把限流误说成填写错误，也避免找回/验证重发在限流时错误声称已发送邮件；不泄露账户、邮件或验证码状态，且未改动任何服务端保护参数。`npm run test:auth`（15/15）、`npm run typecheck`、`npm run lint` 与 `npm run build` 均通过。该源码修复尚未推送或保存为新的 Sites Version，继续遵守“全任务包通过后才上传 GitHub”的约束。
- 2026-08-09（最新）：已用 Sites 控制面回读刷新 `13_evidence/production.json`，替换历史的“Origin 未配置”旧快照。新记录只包含当前私有边界（custom、1 名允许用户、0 个群组/外部访客）、Version #6、环境 revision `7` 与 14 项配置的存在性计数（11 Secret、3 非 Secret）；结构与脱敏回归均通过。它明确仍是 `IN_PROGRESS_PRIVATE_RUNTIME_ACCEPTANCE`，不把注册验证、第二设备、A/B 隔离或数据持久化冒充为完成。
- 2026-08-09：主线程已按 `docs/operation-atlas/MAIN_THREAD_FIX_REQUEST.md` 修复 18 个此前点击无可见效果的桌面、记账、减脂、日程、纪念日、日记、存钱与经期控件。新增客户端交互层将习惯、筛选与提交反馈变为可见状态变化；未登录提交仅产生明确的本次会话记录/提示，不伪造云端持久化。以新本地开发实例运行完整点击采集后，`docs/operation-atlas/button-audit.json` 为 132 个控件、`no_visible_effect=0`、18 个目标均为 `state_changed`；已重建对应 Draw.io 图。`npm run typecheck`、`npm run lint`、`npm run build`、`npm run test:ui-structure`（2/2）与 `npm run test:e2e`（3/3）均通过。
- 2026-08-09（较早快照，已由上两条替代）：S5-T3 私有认证链路已推进到实际 Google OAuth 回跳成功。最新私有部署保持 owner/custom、仅一名允许用户；邮箱注册能进入验证页，但当前 NitroSend 账户在直接发送时返回 provider 级 `account_silenced`，不是应用代码或凭据格式错误。受控的替代邮件凭据已在本机临时安全保存、尚未写入 Sites；下一步是在不公开站点的前提下切换并回放邮箱验证、找回和回滚。
- 2026-08-09：按 `S5-T2-ORIGIN-BOOTSTRAP-001` 成功对既有私有 Version #1 执行一次 owner-only 私有部署，以取得平台分配的 Origin；部署前后都为 owner/custom、1 名允许用户、0 外部访客/群组，未变更公开 audience、未访问用户数据、未运行真实认证/邮件。URL 只以不可逆 SHA-256 记录。随后仅把 `APP_ORIGIN` 作为 Secret 写入 Sites Settings，revision `1→2`、键级条目 `8→9`；当前已部署实例仍绑定 revision `1`，故 revision `2` 必须在完成余下 S5-T2 配置后以受控私有部署应用，不能冒充已运行。Turnstile 写入未假装完成：7 个受控 token 候选中只有 3 个可见同账户，但三个创建请求均为 HTTP `403` / code `10000`，没有 Widget 或键被创建/写入。`13_evidence/origin_bootstrap.json` 与 `13_evidence/sites_runtime_configuration.json` 是当前真源；本地 owner precheck 从 9 项风险收敛到 7 项，仍非 S5-T2 PASS 或 S5-T3。
- 2026-08-09（Origin 引导前的历史快照）：在最新 Owner 直接授权下，私有 Sites Settings 已真实写入并做键级回读：revision `1`、共 8 项，`BETTER_AUTH_SECRET`、Google OAuth、`NITROSEND_API_KEY` 与 `MAIL_FROM` 均标为 Secret；`MAIL_PROVIDER` 和两项隐私常量为非 Secret。该写入来自受控资料/本机生成的稳定认证 secret，未输出、写入或提交任何值；Sites 当时仍无 live/preview URL、访问为 private/custom，未部署。认证运行时保留 Resend 默认，并在显式 `MAIL_PROVIDER=nitrosend` 时经同一 MailPort 支持已验证的 NitroSend REST 后端；回归覆盖 Resend 请求不变、NitroSend 负载形状与失败泛化。以受控来源做的本地存在性预检当时为 9 项风险；该结果不冒充 Sites 完整可运行或 S5-T2 PASS。
- 2026-08-09（本节首条直接授权前的历史只读快照）：继续核验受控邮件与 Turnstile 前置。NitroSend 的 `NITROSEND_SECRET_KEY` 已在子进程中通过其账户读取端点认证，且连接器报告已有验证发送域/默认发件人；但账户当前提供商状态不是 Resend。冻结任务包的第三方依赖决策锁定 Resend HTTPS API（仅以 MailPort 隔离供应商），因此当时未改变默认 Resend 配置、未发送测试邮件。Cloudflare token 可读取唯一可见账户的 Turnstile Widgets，尚无 Personal-WorkBench Widget；官方 API 要求新 Widget 在创建时至少绑定一个允许 hostname，而 taskpack 默认将首个 hostname 设为下游 Sites production Origin，故未创建空 hostname Widget。两项只读事实均不暴露 credential、账号 ID、域名或邮件地址，并确认后续真实 Secret、Origin 与 callback 仍必须在受控 S5-T2/S5-T3 路径中逐项采证。
- 2026-08-09：按 Owner 的受控资料授权完成 `_protected/` 与《云部署必读》附件的最小化、无值盘点。专用 Cloudflare Workers 部署 token 仅在子进程内短暂使用，`wrangler whoami --json` 与 `wrangler pages project list --json` 均成功，未输出、写入或提交 token；`13_evidence/owner_activation.json` 已刷新为 15 项风险（Wrangler 风险为 0、素材权利风险为 0、运行时配置 13 项、运营者/隐私 2 项）。同一次 Sites 控制面只读复核显示当前项目没有 custom domain、没有 production environment entry。全量受控文本配置索引仅发现 Google OAuth 的别名凭据对和 NitroSend 键对；没有 `RESEND_API_KEY`、Turnstile、`APP_ORIGIN`、运营者/隐私联系、发件人或隐私常量的实际非占位赋值。冻结任务包固定为 Resend HTTPS API，经 MailPort 隔离，故未把 NitroSend 键冒充为 Resend，也未猜测域名、注入 Sites Settings、注册 callback、创建外部资源或部署。
- 2026-08-09：Owner 明确确认当前 Hello Kitty 素材可作非商业任意使用。已将该声明绑定到当前 37 个实际运行素材的确定性集合哈希 `092d33323db54d140abca6db940965ea25880487c86fe03fee010744f301384b`，而非虚构为外部原档或第一方代码。`13_evidence/owner_asset_rights_attestation.json` 记录非商业公开范围、现有容器路径约束、来源说明和 `NOT_PERFORMED` 的独立法律验证状态；`verify:assets` 只有在精确 hash、非商业范围、同容器路径和 Owner approval 都匹配时才产生 `PASS_FINAL_AUTHORIZED_ASSETS` / `APPROVED`。`verify:assets -- --public-deploy` 仅验证素材门并已通过，未触发任何部署。本次历史预检曾为 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (16)`，随后先刷新为 15 项，再由本节首条更新为 9 项。该历史快照未注入 Secret、未改 Sites 设置/访问、未部署、未访问用户数据、未上传 GitHub；任何商业化、素材字节变化或授权撤回均需新权利记录并重新生成 manifest。
- 当前推进阶段：`S5_T2_OWNER_ACTIVATION_PRECHECK_IN_PROGRESS`（7 个待核实或配置项；私有 Settings 与 Origin 引导状态见本节首条）
- 2026-08-09（较早快照，后续已刷新）：S5-T2 预检曾为 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`。已保存的 Version #1 链路全部通过：source identity 存在、project_id 与 hosting 一致、私有访问回读与无部署回读均为 true。Sites 控制面复核仍为 active/owner/custom、1 名允许用户、0 外部访客、Version #1、无 live/preview URL；运行时环境 entry count=0，未读取或记录任何值。`verify:assets -- --record` 以任务包输入通过（42 项素材、5 个 mask），但正确保留 `PRIVATE_CANDIDATE_PASS_PUBLIC_DEPLOY_BLOCKED` / `BLOCKED_ASSET_RIGHTS`。预检脚本现仅记录 APP_ORIGIN、回调和 Wrangler 到期的存在性/布尔状态，并已加入 Saved Candidate 一致性检查；Owner activation 与 release-evidence 脱敏回归、lint、typecheck 均通过。未配置 Secret、未改 Sites 设置/访问、未部署、未访问用户数据、未上传 GitHub。
- 2026-08-09：S5-T1 已真实保存为 Sites 私有 Version #1。Sites source `main` 轻量回读为精确冻结 MetaDatabase commit `cf7b156e76376f9e7783b1b1d68f5e8b1f09eb85`；没有强制推送或覆盖远端。归档从该 commit 的 `Personal-WorkBench` tree `b831d4564fc01352edfa3f5f26020965f3825df4` 构建，local SHA-256 为 `dd61f9b1bfbefd610276b84121daffcf93a00fb8e805916fd18a91d76bf6976d`，且 `dist/server/index.js` 与 `dist/.openai/hosting.json` 已验证。PWB-S5-SOURCE-PROJECTION-001 的 `3eaf351c` 仅作为 tree-identical 独立审计身份，不替代实际 Sites source commit。保存前后均为 owner/custom、1 名允许用户、0 外部访客、0→1 个 Version、无 live/preview URL；运行时配置 entry count=0，未读取或记录任何值。真实证据见 `13_evidence/saved_version.json`；未部署、未改访问、未配置 Secret、未访问用户数据、未上传 GitHub。
- 2026-08-09：独立 S4-T3A 已对精确 `cf7b156e76376f9e7783b1b1d68f5e8b1f09eb85` / tree `2733e8de41616ea442701da41a7ac35e13d3b978` 给出 `READINESS_PASS`（仅解锁私有 S5-T1，非 15/15、非 release candidate、非公开授权）。其 SHA-256 封存包为 `3620486f83814e1d178b7936da3b687bf417702eefc4ea31265b30a419ff758a`；该结论未修改产品、任务包或 Sites。
- 2026-08-09：S5-T1 已从同一精确 commit 的 `Personal-WorkBench` 子树在临时副本通过 `npm run check`、`npm run build` 与 `verify:release`，并生成 archive SHA-256 `bb96d8698d93a23d45ba1b9e9a116e450749ebcd4b3c63ecda188040071a57d3`。Sites 控制面复核为 active/owner/custom、1 名允许用户、0 名外部访问者、0 个 Version、无 live/preview URL。向空的专用源码库 `main` 非强制推送该精确 commit 的两次标准传输和一次仅 HTTP buffering 调整的传输均收到 `HTTP 500`；最终远端 heads=0，未保存 Version、未改访问、未部署、未配置 Secret、未访问用户数据、未上传 GitHub。不得以不同 Git commit 的 project-only source projection 静默替代冻结 commit 绑定。
- 2026-08-09：为保留冻结项目树而非静默降级，新增 `PWB-S5-SOURCE-PROJECTION-001`。它将 MetaDatabase commit `cf7b156e` / root tree `2733e8de` 的 Personal-WorkBench subtree tree `b831d456` 投影为无父 Sites source commit `3eaf351c`；验证脚本双次复现同一 commit、同一 tree 和 293 个受控文件，输出 `PASS_SOURCE_PROJECTION_CONTRACT`，且不做远程动作。该合同只恢复后续私有 S5-T1 的 source transport 路径，不代表产品 PASS 或公开授权。
- 2026-08-09：已创建 `PWB-S4-S5-SEQUENCE-001`，将不可满足的 `S4-T3 → S5-T1` 证据循环拆为 `S4-T3A` 独立就绪审查、私有 Candidate 的 S5-T1 至 S5-T4 真实采证、`S6-T1` 15/15 最终独立验收和 `S6-T2` 公开 audience 确认。增补通过 `npm run test:acceptance-sequence`（3/3）和对冻结目录执行的 `npm run validate:acceptance-sequence`；后者返回 `PASS_SEQUENCE_ADDENDUM_INTEGRITY_ONLY` / `NOT_PRODUCT_ACCEPTANCE`。它以五个冻结文件 SHA-256 绑定输入，不改原任务包、Oracle、阈值、视觉或架构，并明确禁止以本地/UNKNOWN/NOT_RUN/WAIVED 冒充产品 PASS。
- 2026-08-09T09:10:10+10:00：针对精确 Subject `4f96d9262204be42729ea70f64141b8bf289357f` 的独立审查 P1，已完成本地整改；本阶段收尾将其冻结为新的本地 commit：账户页在敏感跨设备启用前展示版本化中文隐私说明（含收集字段、目的、D1/R2 权威存储、无数据驻留保证、保留/导出/删除/撤回、联系渠道和非医疗边界）；所有自定义写路由执行 same-origin Origin/CSRF 边界；账户删除要求 10 分钟内的新 Better Auth session；运行时支持冻结 binding `MAIL_FROM`，并在两个 sender 名同时冲突时 fail closed。`lint`、`typecheck`、聚焦 auth/API、privacy/account-lifecycle/legacy/R2/tenant/module、e2e 与 build 已通过。未访问 Sites、GitHub、真实 provider、D1/R2 或任何用户数据。
- 2026-08-09：首个冻结候选 `3210a4737e575978a627a9a8b6d092c2d9162a1e` 的独立审查 Round 1 为 `BLOCKED`；其正式 S4-T3 追溯/15 项验收/Sites 私有 Version 证据尚不存在，且不能由本地 `verify:release` 替代。该结论保留为历史审查事实，新的修复不会倒改它。
- 2026-08-09：已修复审查发现的本地 P1：服务端敏感云端门现在要求当前 policy 的明确同意、未撤回和 active 删除状态；覆盖账单、体重、日记、经期、日记图片与含敏感内容的旧数据导入。账户删除改为 R2 删除失败即保持 pending 并可重试，不再删除元数据/用户。替代候选已在本地提交，仍未创建 Sites Version、修改 Sites 环境、改变访问策略、部署或上传 GitHub。
- 2026-08-09：本地 P0 验证已重跑通过（unit、privacy、modules、e2e、quality、visual、recovery、check、build 与干净环境 `verify:release`）；`verify:release` 仍明确为 `NOT_ISSUED_PRE_VERIFIER`，不可替代 S4-T3 独立裁决。尚未创建 Sites Version、修改 Sites 环境、改变访问策略、部署或上传 GitHub。
- 2026-08-09：生产/运维预检证据已收敛为状态、时延、存在性和脱敏引用；不再写入命令输出、响应正文、原始嵌套证据、本机绝对路径或配置值。对应回归由 `test:release-evidence` 覆盖。
- 2026-08-08T20:41Z：现有 ChatGPT Sites 项目处于 `active` 且当前身份为 `owner`，但仍无已保存版本、预览/生产 URL 或生产环境变量；未创建版本、未部署、未上传 GitHub。
- 最新 `npm run verify:owner-activation`：`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`（17 项风险）。Cloudflare CLI 未登录、生产环境变量为空、公开授权素材记录未落盘仍是当前阻断。
- 本地构建已通过；`npm run test:s2` 通过 schema、认证契约、租户隔离、API 和 R2 约束，但 Saved Candidate 真实认证回放仍为 `NOT_RUN`。
- `S5-T3` 保持下游：本地路由与鉴权探针可达；真实 OAuth/邮箱注册/找回/会话链路与生产域回放尚未执行。
- `PRE_S5_T1_LOCAL_PREFLIGHT` 已通过（仅本地/非生产证据化）；任务包 canonical `S5-T1`（保存私有 Version）仍为 `NOT_RUN_BUILD_LAST_MILE`，不得由本地预检替代。
- `S5-T2` 当前状态：`BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`（当前剩余阻断为 `wrangler` 认证态与 `asset_manifest` 公开授权状态）。
- `S5-T3` 当前状态：`BLOCKED_LOCAL_PRODUCTION_SMOKE_PRECHECK`（本地路由与鉴权探针可达；阻断在于真实 OAuth/邮箱注册/找回/会话链路与生产域回放尚未执行）
- 2026-08-09T06:52:26+10:00：补齐本地邮箱验证恢复 UX：注册成功后引导至验证页；验证页可安全地重发验证邮件；验证完成后回到登录页显示登录指引。该改动仅通过同源常量回调，不在 URL 中放置邮箱，也未触及 Sites、密钥、公开素材或 S5 生产门状态。
- 2026-08-09T07:03:09+10:00：S5-T2 预检证据已完成脱敏加固。Sites 控制面仍显示 owner 权限、私有自定义访问、0 个保存版本、无预览/生产 URL、0 个生产环境变量；本地预检仍为 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`，但不再将密钥片段、邮箱、CLI 原文或绝对本机路径写入证据。
- 2026-08-09T07:19:50+10:00：发布前置脚本现明确为 `PRE_S5_T1_LOCAL_PREFLIGHT`，不冒充任务包的 `S5-T1` Saved Version 验收。默认探针改为无密钥受控路由 harness（503/200），不会隐式启动 dev 或加载本地变量；只有显式 `S2_LOCAL_AUTH_ORIGIN` 才探测操作者已启动的服务。干净环境 `npm run verify:public-launch` 通过，但报告仍为 `public_deploy_eligible=false`、4 个外部门未满足；未创建 Sites Version、未部署、未改环境、未上传 GitHub。
- 公开部署状态：`BLOCKED_ASSET_RIGHTS`；`asset_manifest` 尚无最终公开授权素材记录，且本地预检不授予 Deploy 权限。
- 验收脚本已兼容非交互场景：`npx wrangler whoami` 若提示 400/未登录，会在 `13_evidence/owner_activation.json` 输出 `checks.wrangler.auth_recovery_hint`；本地 token 即使过期也会尝试执行 `whoami`，以保留可复现失败证据；如配置过期，也可通过 `CLOUDFLARE_API_TOKEN` 验证（非交互环境）。
- 里程碑状态：
  - `npm run test:quality`：通过，`13_evidence/quality.json` 为 `PASS_LOCAL_QUALITY`
  - `npm run test:visual`：通过，`13_evidence/visual/manifest.json` 为 `PASS`
- `npm run test:resilience`：通过，`13_evidence/resilience.json` 为 `PASS_LOCAL_RETRY_RESILIENCE`
- `npm run verify:public-launch`：本地前置检查通过，产出 `13_evidence/public_launch_preflight.json`；不代表 canonical `S5-T1` 已完成或可部署。
- `npm run verify:owner-activation`：再次失败，产出 `13_evidence/owner_activation.json`，状态 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`。
  - 已使用本地完整占位变量演练时阻断降至 2 条：
    1) 未检测到 `wrangler oauth_token`
    2) `asset_manifest` 仍处于 `BLOCKED_ASSET_RIGHTS`
- `npm run verify:production-smoke`：当前 BLOCKED，产出 `13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`
- `npm run verify:ops-projection`：当前 BLOCKED，产出 `13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`
- `verify:release` / `taskpack` 预检沿用 S5-T1 现状
- S5-T2 可执行清单已补齐在 [RUN_CONTRACT_S5_T2.md](/Users/linzezhang/.codex/worktrees/ef81/MetaDatabase/Personal-WorkBench/RUN_CONTRACT_S5_T2.md)（含复制执行命令与证据刷新要求）

## 已改动

- `server/security/privacy-consent.ts`
  - 新增敏感云端处理的唯一服务端门：要求当前版本同意、未撤回且账户未处于 pending 删除；普通模块不受阻塞。
- `app/api/workbench/[resource]/*`、`app/api/workbench/files/*`、`server/files/private-files.ts`
  - 敏感记录与日记图片在读取、创建、替换以及幂等记录写入前均执行服务端门；本人删除路径保持可用以支持数据清除。
- `server/data/legacy-import.ts`、`app/api/workbench/legacy-import/*`
  - 含账单、体重、日记、经期或日记图片的导入，在写入导入状态/幂等键前必须通过同意门；仅普通数据的导入仍可预览。
- `server/data/account-lifecycle.ts`
  - R2 对象删除失败或缺失绑定时 fail-closed，保留 pending 状态、恢复口令、文件元数据和后续删除步骤用于安全重试。
- `tests/privacy.test.mts`、`tests/r2.test.mts`、`tests/legacy-import.test.mts`、`tests/account-lifecycle.test.mts`、`tests/api-contract.test.mjs`
  - 覆盖未同意、旧 policy、撤回、日记对象、旧数据导入与 R2 删除中断/重试的负向和恢复路径。

- `app/_components/workbench/outbox-queue.ts`
  - 新增 outbox 队列读写与重放策略模块，提炼 `read/write/append/replay` 逻辑。
- `app/_components/workbench/todo-page-client.tsx`
  - 将待发队列读写与重放改为共享 outbox 模块，`503`/冲突/网络异常下不继续无序重发，保留未完成动作。
- `tests/outbox-replay.test.mts`
  - 新增离线重放回归：成功、冲突、503、网络异常场景。
- `scripts/verify-offline-replay.mts`
  - 新增离线重放验证脚本，产出 `13_evidence/resilience.json`。
- `RUN_CONTRACT_S4_T2.md`
  - 新增本阶段任务合同。
- `RUN_CONTRACT_S4_T3.md`
  - 新增本阶段任务合同与候选冻结预检收束标准。
- `scripts/verify-release.mjs`
  - 保持 release 预检脚本与证据链不变（`13_evidence/verifier.json`）。
- `RUN_CONTRACT_S5_T1.md`
  - 新建本阶段任务合同。
- `scripts/verify-public-launch-preflight.mjs`
  - 新增发布前置统一预检脚本；默认使用无密钥受控路由 harness，不隐式启动 dev 或加载本地变量。显式传入 `S2_LOCAL_AUTH_ORIGIN` 时才探测操作者已启动的本地服务。
- `package.json`
  - 新增 `verify:public-launch` 脚本。
- `scripts/verify-owner-activation.mjs`
  - 新增 Owner 生产激活本地预检脚本，输出 `13_evidence/owner_activation.json`。
- `scripts/verify-owner-activation.mjs`（本次更新）
  - 增加 `SITES_BINDINGS_CONTRACT.json` 与 `13_evidence/verifier.json` 的一致性校验：D1/R2 绑定一致性、约定密钥覆盖、release 预检状态。
- `scripts/verify-production-smoke.mjs`
  - 新增生产链路预检脚本，输出 `13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`；预检报告只保留脱敏状态，不保留 Origin、响应正文或命令原文。
- `scripts/verify-ops-projection.mjs`
  - 新增状态系统投影前置脚本，输出 `13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`；不记录 adapter endpoint、token 或响应正文。
- `package.json`
  - 新增命令别名：`verify:production-smoke`、`verify:ops-projection`、`test:unit`、`test:recovery`、`test:regression`。
- `server/data/account-lifecycle.ts`
  - 将隐私常量对齐任务包公开版本：`ACCOUNT_PRIVACY_POLICY_VERSION = "2026-08-03.v2"`，`ACCOUNT_PRIVACY_NOTICE_SHA256 = "5c5403...a2f7e956"`，消除占位 hash 导致的本地隐私证据误报。
- `RUN_CONTRACT_S5_T2.md`
  - 新增本阶段任务合同（Owner 生产激活前置）并对齐执行边界。
- `RUN_CONTRACT_S5_T3.md`
  - 新增 S5-T3 预检合同。
- `app/auth/_components/auth-flow.ts`
  - 集中认证请求与受控回调路径，新增邮箱验证重发请求契约。
- `app/auth/_components/auth-form.tsx`
  - 注册后进入验证页；验证页渲染重发邮件表单；验证成功后显示登录指引。
- `tests/auth-contract.test.mts`、`tests/e2e-smoke.test.mjs`
  - 覆盖重发验证邮件、无邮箱泄露的回调、验证页与验证后登录提示的构建产物渲染。
- `scripts/verify-auth-contract.mjs`
  - 将认证契约校验对齐至新的请求构造模块。
- `scripts/verify-owner-activation.mjs`
  - 将 S5-T2 证据降为存在性、状态与匹配结论；剔除密钥片段、个人邮箱、CLI 输出、原始嵌套证据与绝对本机路径。
- `tests/owner-activation-evidence.test.mjs`
  - 以临时目录和伪造值验证证据 JSON 不泄漏配置或命令输出。
- `package.json`
  - 新增 `test:owner-activation` 回归入口。
- `13_evidence/production.json`
  - 从任务包封存模板初始化，作为 S5-T3 证据槽位。
- `13_evidence/ops_projection.json`
  - 从任务包封存模板初始化，作为 S5-T4 证据槽位。

## 验证命令与结果

- 本轮安全修补（2026-08-09）：`npm run lint`、`npm run typecheck`、`npm run test:unit`、`npm run test:privacy`、`npm run test:account-lifecycle`、`npm run test:legacy-import`、`npm run test:modules`、`npm run build`、`npm run test:e2e`、`npm run test:quality`、`npm run test:visual`、`npm run test:recovery`、`npm run check`、`npm run test:release-evidence` 均通过。
- 干净环境 `npm run verify:release`：通过，状态 `PASS_BUILD_LAST_MILE_READINESS`，verdict 仍为 `NOT_ISSUED_PRE_VERIFIER`；不构成 S4-T3 或 S5-T1 通过。

- `npm run test:quality`（通过）
- `npm run test:visual`（通过）
- `npm run test:resilience`（通过）
- `python3 12_scripts/verify_taskpack.py`（通过；`PASS_FOR_SEALED_TASKPACK`）
- `npm run verify:release`（通过；`13_evidence/verifier.json` 写入）
- `npm run test:s2`（通过）
- `npm run verify:public-launch`（PRE-S5-T1 本地检查通过；`13_evidence/public_launch_preflight.json` 写入；不等同于任务包 S5-T1）
- `npm run verify:owner-activation`（当前 BLOCKED；`13_evidence/owner_activation.json` 写入）
- `npm run verify:production-smoke`（当前 BLOCKED；`13_evidence/production.json` 与 `13_evidence/production-smoke-run.json`）
- `npm run verify:ops-projection`（当前 BLOCKED；`13_evidence/ops_projection.json` 与 `13_evidence/ops_projection-run.json`）
- 本轮本地复测（2026-08-05T23:02:26-32Z）：`npm run verify:production-smoke`、`npm run verify:ops-projection` 在本地 3000 端口均可访问，`/api/auth/public-config` 与 `/api/workbench/profile` 已达标（200/401），三类 `/api/ops/*` 均返回 200，但阻断仍在真实生产 OAuth/邮件回放链路未执行。
- 最新一次 `npm run verify:owner-activation`（2026-08-05T21:37:34.215Z）：`checks.wrangler.auth_mode` 在缺失 `wrangler` 登录时仍为 `BLOCKED`，阻断项固定为：
  - `wrangler oauth_token` 缺失（需执行登录）
  - `OWNER_APPROVAL.production_side_effect_authorization=false`
  - `asset_manifest` 仍 `BLOCKED_ASSET_RIGHTS`
  `generated_at` 已刷新。
  注：本轮使用最小化占位生产环境变量（包含完整隐私哈希）复跑，仅保留上述 3 项阻断。
- 次次运行（2026-08-05T21:41:30.723Z）：`npm run verify:owner-activation` 再次返回 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK`，三项阻断未变化。
- `npm run test:auth-runtime`（通过，`PASS_LOCAL_NO_SECRET_AUTH_BOUNDARY`；默认不启动本地 dev，显式 Origin 模式才探测已启动服务）
- `npm run test:e2e`（通过）
- `npm run test:legacy-import`（通过）
- 本轮本地认证恢复修补（2026-08-09T06:52:26+10:00）：`npm run test:auth`（5/5 通过）、`npm run build`（通过）、`npm run lint`（0 error；4 项既有 warning）、`npm run test:e2e`（3/3 通过）。这些仅证明本地候选；真实邮箱、Google OAuth、Turnstile 与生产域回放仍未执行。
- `npm run typecheck` 已通过：待办操作错误消息已收敛为安全回退文案，临时 `tests/pw-temp.spec.ts` 已被精确排除且保持未跟踪；未以跳过项目源码检查的方式绕过 TypeScript。
- 本轮 S5-T2 证据加固（2026-08-09T07:03:09+10:00）：`npm run test:owner-activation`（2/2 通过）、`npm run lint`（0 error；4 项既有 warning）、干净环境 `npm run verify:owner-activation`（预期 `BLOCKED_LOCAL_OWNER_ACTIVATION_PRECHECK (17)`）；生成证据已确认无 `value`、`values`、`stdout`、`stderr` 或 `raw` 字段。

证据：
- `13_evidence/quality.json`
- `13_evidence/visual/manifest.json`
- `13_evidence/resilience.json`
- `13_evidence/verifier.json`
- `13_evidence/auth.json`
- `13_evidence/tenant_matrix.json`
- `13_evidence/r2.json`
- `13_evidence/auth-saved.json`
- `13_evidence/auth-local-runtime.json`
- `13_evidence/public_launch_preflight.json`
- `13_evidence/production.json`
- `13_evidence/production-smoke-run.json`
- `13_evidence/ops_projection.json`
- `13_evidence/ops_projection-run.json`

## 未解决风险

- 正式 `S4-T3`/S6-T1 的 15/15 验收仍未通过：首个冻结候选的独立 Round 1 已确认缺少正式追溯、精确 subject binding 和真实 Sites 私有 Version 证据；当前候选仅有 S4-T3A `READINESS_PASS`，其唯一作用是允许私有 S5-T1 采证。
- `PWB-S4-S5-SEQUENCE-001` 已将 S4/S5 的验收顺序环以 Owner 授权的项目内增补固定并由 SHA 校验；它尚未替代任何真实 Candidate、provider、D1/R2、回滚或 15/15 最终证据。冻结任务包原件保持不变。
- 通用 Verifier 的任务包导入器未识别该任务包的 canonical manifest 布局；不可伪造导入成功或正向报告，需使用兼容适配器/人工任务包追溯证据完成正式裁决。

- S5-T1 source linkage 已由真实 ref 回读解决：本 run 的非强制 projection 推送因远端已有提交被拒绝，随后只读确认 Sites `main` 已指向精确 `cf7b156e`，故没有覆盖远端，直接保存该精确 source 的私有 Version #1。PWB-S5-SOURCE-PROJECTION-001 继续保留为可审计的 tree-identical build/archive 身份；`saved_version.json` 已同时记录冻结 source、projection audit 与 provider Version。此结果不证明任何运行时 Secret、真实认证、D1/R2、跨设备或公开部署要求。

- S5-T2 的剩余外部门已被拆分为可复验事实，不能以占位值替代：当前无可用 Wrangler 身份、Sites runtime 配置不存在、APP_ORIGIN/Google callback/邮件发送域/Turnstile/运营者和隐私联系信息未完成，以及最终公开授权 Hello Kitty 原始素材与来源/权利记录缺失。`OWNER_APPROVAL.json` 的方向与生产副作用授权仍为 APPROVED/true，但不等于已拥有外部凭据或公开素材权利。

- 未登录 wrangler（`wrangler whoami` 失败）：仅影响 CLI 侧的 Pages 核验；Sites 控制面已独立复核当前身份为 owner，但这不替代运行时环境、素材授权或真实认证链路验收。
- 当前机本地未落盘可用 wrangler token（默认路径 `~/Library/Preferences/.wrangler/config/default.toml` 目前不存在可用 `oauth_token`）
- `wrangler whoami` 常见失败（400 Bad Request）可先执行 `wrangler logout` 后 `wrangler login`，再重试 `whoami` 与 `pages project list --json`
- 已尝试 `npx wrangler login --browser=false --scopes pages:write --scopes d1:write --scopes workers:write`（2026-08-05 21:35）：
  - 已抓到授权链接并等待回调，但本次会话 2 分钟超时未完成回调（未接收到授权码）。
  - 观察到日志落盘：`/Users/linzezhang/Library/Preferences/.wrangler/logs/wrangler-2026-08-05_21-35-09_011.log`，结尾错误为 `user oauth authorization timeout`。
  - 需要在外部浏览器打开授权链接并完成 callback 后，重试本机登录命令并继续 `npx wrangler whoami`。
  - 实测提示：`localhost:8976` 会被 callback 命中；若回调失败，可手动核验回调 URL 最终应含 `code` 与 `state`，并避免 `127.0.0.1` 转发误配。
- 已再次尝试 `npx wrangler login`（2026-08-05 21:39）：
  - 本次再次打印 OAuth 授权链接并等待 2 分钟超时退出，未接收到授权码。
  - 观察到日志落盘：`/Users/linzezhang/Library/Preferences/.wrangler/logs/wrangler-2026-08-05_21-39-24_141.log`，同样记录 `user oauth authorization timeout`。
- 证据状态更新：`13_evidence/owner_activation.json` 的 `checks.wrangler.whoami.reason` 仍为“wrangler 配置缺失/异常”，且 `generated_at` 已更新为 `2026-08-05T21:41:30.723Z`。
- 当前建议保留：在外部环境执行 `npx wrangler login`（`--browser=false`，并完成回调）后，再在本机执行 `npx wrangler whoami` 与 `npx wrangler pages project list --json`。
- `RUN_CONTRACT_S5_T2.md` 已补充上述非交互登录命令与回调说明（含可复制链接流程）。
- 本地 `owner_activation` 已能区分 `auth_mode`：`LOCAL_TOKEN`（本地 token 可用） / `CLOUDFLARE_API_TOKEN`（非交互 token） / `SKIP`（认证不可执行）
- `owner_activation` 已带入 `checks.wrangler.config`：可直接核验本机 `.wrangler/config/default.toml` 中 `expiration_time` 与 token 状态，若已过期请先 `wrangler login` 重置会话。
- 当前证据链已带入 `owner_activation` 的 wrangler 认证恢复提示字段，可直接看 `checks.wrangler.whoami.auth_recovery_hint` 获取重登建议。
- 必需生产密钥已在本地模拟校验中临时注入验证，外部仍缺失实际可用的 Sites Secrets（`BETTER_AUTH_SECRET`、`APP_ORIGIN`、`GOOGLE_*`、`RESEND_API_KEY`、`TURNSTILE_*`、`LEGAL_OPERATOR_NAME`、`PRIVACY_CONTACT_EMAIL`、`MAIL_FROM`/`AUTH_FROM_EMAIL`）
- `SITES_BINDINGS_CONTRACT.json` 约定密钥在实际部署环境暂未写入核验（本地仅验证清单完整性）
- `SITES_BINDINGS_CONTRACT.json` 的 `project_id` 仍是 `generated_by_sites_and_never_hand_invented` 占位符，需在正式 provision 后复核与生产配置一致
- `OWNER_APPROVAL.production_side_effect_authorization` 为 `true`
- `CLOUDFLARE_API_TOKEN` 未设置（非交互 `wrangler` 调试时的替代认证入口）
- `PRIVACY_POLICY_VERSION` 与 `PRIVACY_NOTICE_SHA256` 可通过环境模拟对齐任务包值（`2026-08-03.v2` 与 SHA）。
- 公开素材授权状态 `BLOCKED_ASSET_RIGHTS` 仍需处理
- `13_evidence/verifier.json` 与 `13_evidence/public_launch_preflight.json` 仅为本地预检，不代表正式上线裁决。
- 公开部署仍受素材授权与生产渠道凭据准备状态限制。
- `npm run verify:production-smoke` 已确认本地 401 鉴权与 `/api/auth/public-config` 可达，阻断收敛到“真实 OAuth/邮箱注册/找回/会话链路”外部执行前置。
- `npm run verify:ops-projection` 已确认 `/api/ops/status`、`/api/ops/ovh`、`/api/ops/pdb` 可达与鉴权（401→200）路径闭环，残留阻断由 `production-smoke` 未通过导致的联动红线。
- 本轮 `production-smoke` 风险收敛为 `1` 项（真实回放未执行），`ops-projection` 风险收敛为 `1` 项（S5-T3 阻断），说明本地可复现预检已进入外部门槛阶段。

## 下一步

### 最新优先

1. 使用可核验的受控测试账号，在现有私有 Version #7 仅做一次邮箱注册/验证/登录、Google callback、A/B 隔离写入与跨设备历史读回；不得选择个人账户、绕过认证/隐私门或反复撞击限流。
2. 将 D1/R2 对账、负向 provider/recovery 路径与上述回放绑定到当前私有版本；公开发布、S5-T4/S6 和 GitHub 上传仍然禁止。

### 历史记录（部分事项已完成；以上述最新优先项为准）

1. Owner 在对话外完成真实 Sites runtime 配置、Cloudflare/Wrangler 登录、Google callback、邮件发送域、Turnstile 与运营者/隐私信息；不得在仓库或对话中提供 Secret。
2. 保持当前 37 个素材的精确字节、容器路径和非商业范围；任何商业化、素材替换或授权撤回都必须先更新 `owner_asset_rights_attestation.json` 并重跑 `verify:assets -- --record`。
3. 完成运行时前置后在独立 run 重跑 [RUN_CONTRACT_S5_T2.md](/Users/linzezhang/.codex/worktrees/ef81/MetaDatabase/Personal-WorkBench/RUN_CONTRACT_S5_T2.md) 的预检；仅 risks 清零后才能推进 S5-T3 的受控私有部署、真实 OAuth/邮箱/Turnstile 与回滚采证。S5-T4、S6-T1 和 S6-T2 仍在其后；GitHub 上传继续保持全部任务包完成后。
