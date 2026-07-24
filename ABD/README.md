# ABD Product Design TaskPack `0.0.0.1`

这是ABD最终开发任务包。它不是已完成的软件，而是无歧义、机器可执行、可验收、可回滚的开发/部署/运行合同。

## 当前开发状态

- `S00/P01`、`S00/P02`、`S00/P03` 与 `S00/P04` 已分别由独立证据标为 `PASS`；
- 任务包自身的 `PASS` 只表示“开发合同可交接”，不表示 ABD 已上线、已部署或已验证收益；
- Stage 0 已完成 4/4 个 Phase；本地整体复审的 45/45 门、定向测试 54/54、全回归 206/206 与任务包校验 49/49 均为 `PASS`；
- Stage 0 已通过 GitHub PR #58 合并到 `main`；两条 main CI 成功记录已固化为不可变交付收据，并由离线 Git 历史再次验证；
- `S01/P01` 已完成客户新闻稿与客户结果合同，独立 Oracle 67/67、定向测试 80/80、全回归 286/286 与任务包校验 49/49 均为 `PASS`；证据下一状态严格为 `S01/P02_READY_NOT_STARTED`；
- `S01/P02` 已完成客户 FAQ 与假设登记册，独立 Oracle 93/93、定向测试 239/239、全回归 525/525 与任务包校验 49/49 均为 `PASS`；证据下一状态严格为 `S01/P03_READY_NOT_STARTED`；
- `S01/P03` 已冻结 21 条唯一产品需求、5 条业务线、18 个功能模块、8 条主流程和 13 条显式安全错误路径；含外部报告门的独立 Oracle 110/110、定向测试 132/132、全回归 658/658 与任务包校验 49/49 均为 `PASS`；
- `S01/P04` 已冻结 31 个指标、五项非现金收益测量、成本/ROI 未知默认和 19 条前瞻 kill criteria；整体复审发现的四条未测需求已修复，独立 Oracle 133/133、定向测试 157/157、全回归 815/815 与任务包校验 49/49 均为 `PASS`；
- `S01 整体复审` 的 61/61 门、定向测试 87/87、全回归 902/902、TaskPack 49/49、付费依赖扫描与 7/7 回滚均为 `PASS`；Stage 1 已通过 GitHub PR #64 合并到 `main`，两条 main CI 成功记录、A$0 交付门和离线 Git 历史已固化为不可变交付收据；
- `S02/P01` 已冻结 24 个官方一手来源、23 条平台事实与 9 条监管控制，共 32 个唯一 claim；含外部报告门的独立 Oracle 88/88、定向测试 158/158、全回归 1060/1060、TaskPack 49/49、付费依赖扫描与 7/7 回滚均为 `PASS`，证据下一状态严格为 `S02/P02_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P01` 明确拒绝把 TAB Studio/Web Services、Sportsbet 自动化、Gmail、Cloudflare 或 OVH 写成已授权或已连接能力；Cloudflare 中国网络不属于 A$0 范围，普通全球网络上的中文界面不等于中国大陆境内加速、可用性或可达性保证；
- `S02/P02` 已冻结 8 篇一手论文、14 条可追溯模型与风险主张，以及 18 个明确不得冒充论文推导值的本地阈值；含外部报告门的独立 Oracle 90/90、定向测试 161/161、全回归 1221/1221、TaskPack 49/49、付费依赖扫描与 8/8 回滚均为 `PASS`，证据下一状态严格为 `S02/P03_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P02` 只固化市场先验、校准与 proper scoring、不建议区域、异常敏感性和受限凯利的研究边界；未训练或执行模型、未回测、未验证全部市场、未接入账户、未部署，也不证明任何收益或风险保证；
- `S02/P03` 已在固定 Git commit 上审计 flumine、penaltyblog、OddsHarvester 等 6 个公开仓库，逐项冻结 adopt/adapt/reject、许可证和来源合同决定；4 个 MIT、1 个 Apache-2.0、1 个未检测到许可证，未检测到许可证的仓库禁止代码复用；含外部报告门的独立 Oracle 93/93、定向测试 218/218、全回归 1439/1439、TaskPack 49/49、付费依赖扫描与 8/8 回滚均为 `PASS`，证据下一状态严格为 `S02/P04_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未单独上传 GitHub；
- `S02/P03` 没有复制候选代码、clone 仓库、安装依赖、调用外部 API/账户、绕过站点控制或花费新增现金；仓库许可证不替代网站、数据、API、账户、再分发或商业服务条款，GitHub 自动许可证检测也不构成法律许可；
- `S02/P04` 已把 P01–P03 的显式未知、未验证前置、模型主张、本地阈值、复用限制和监管适用性归并为 26 个明确开放缺口；Stage 2 整体复审发现其中 3 个 gap 缺少直接 counterevidence，已新增 CE-S02-P04-020 至 022 并把 26/26 双向覆盖升级为 fail-closed Oracle 门；26 个缺口仍全部保持 `OPEN_EXPLICIT`，已解决 0、静默缺口 0，登记、反证或安排复审均不等于解决；四个中间 Phase 均仅本地开发，尚未单独上传 GitHub；
- `S02 整体复审` 已冻结并解决 4 条 findings，覆盖跨 Phase 来源图、历史 commit/收据重放、A$300/A$0、无自动下单、无收益保证、全回归与回滚门；GitHub 上传预检暴露的绝对本地路径变异测试跨平台缺口已通过 POSIX/Windows/UNC/file URI 统一拒绝规则修复；独立 Oracle 63/63、定向测试 339/339、全回归 2155/2155、TaskPack 49/49、付费依赖扫描与 13/13 回滚均为 `PASS`；Stage 2 已通过 GitHub PR #65 合并到 `main`，两条 main CI 成功记录、A$0 交付门和离线 Git 历史已固化为不可变交付收据；
- `S03/P01` 已冻结 28 条中文术语与机器映射、5 类日常界面、3 条通用机器词拦截模式和逐词展示策略；含外部报告门的独立 Oracle 180/180、定向测试 164/164、全回归 2319/2319、TaskPack 49/49、付费依赖扫描与 5/5 回滚均为 `PASS`，下一状态严格为 `S03/P02_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未上传 GitHub；
- `S03/P01` 只冻结中文术语与界面暴露合同，不声称首页、建议卡、错误路径或无障碍界面已实现、部署或完成可用性验证；源代码、机器字段和不可渲染证据保留英文标识，任何进入用户界面的内容必须重新通过中文门；
- `S03/P02` 已冻结每日唯一建议卡的 19 个根字段、7 段固定展示顺序、建议/不建议双色加文字与符号冗余、三态倒计时、四个首要答案、理由和五项失效条件；含外部报告门的独立 Oracle 194/194、定向测试 235/235、全回归 2554/2554、TaskPack 49/49、付费依赖扫描与 5/5 回滚均为 `PASS`，回放入口为 `tests/S03/P02_test.py` 与 `AC-S03-P02`，下一状态严格为 `S03/P03_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未上传 GitHub；
- `S03/P02` 的推荐样例全部是冻结的合成合同向量；结构化四答案扫描门只证明“做什么、在哪做、金额和最低赔率”位于固定首屏行动区，不冒充真人十秒理解、无障碍、跨设备或生产界面验收，这些仍属于 `S03/P04`；
- `S03/P02` 未执行模型、选择真实市场、连接平台账户、部署界面或提交订单；任何输入缺失、过期、赔率不足、上游门失败或不利扰动动作翻转均降级为“不建议”，用户仍是唯一可完成最终下单的人；
- `S03/P03` 已冻结当前权威合同中 49 个失败原因、38 个本地安全动作和 72 条来源覆盖引用；每个原因只映射一个动作，多失败状态按唯一优先级确定一个结果，未知或畸形输入统一停止并保留证据；含外部报告门的独立 Oracle 302/302、定向测试 460/460、全回归 3014/3014、TaskPack 49/49、付费依赖扫描与 6/6 回滚均为 `PASS`，回放入口为 `tests/S03/P03_test.py` 与 `AC-S03-P03`，下一状态严格为 `S03/P04_READY_NOT_STARTED`；本 Phase 仅本地开发，尚未上传 GitHub；
- `S03/P03` 的“全部”严格限定为当前版本已声明且可由权威文件枚举的失败类别；未来 Phase 新增原因时必须显式扩展目录、映射、覆盖引用和 Oracle，不得把未知状态静默归入已有原因；
- `S03/P03` 只提供确定性的中文错误说明与本地下一步指引，不执行自动重试、真实下单、外部账户/API 访问、模型、部署或付费动作，也不放宽证据、数值、风险、安全或来源合同门；
- `S03/P04` 已冻结手机、电脑、低带宽、颜色辨识受限、字号放大至 200%、仅键盘和屏幕阅读器线性阅读共 7 类结构化设计合同，以及覆盖全部 4 个核心任务的 21 个保守完成预算；最近秩法中位数为 540 秒、95 分位为 840 秒，分别不超过 600 秒与 1200 秒硬门；整体复审把 P03 的 49 个失败原因全部绑定到 `失败状态→失败原因→下一步→安全提示` 的键盘焦点与屏幕阅读器线性顺序，并逐项重放唯一中文下一步；
- `S03/P04` 的 21 个数值是冻结的保守任务预算，不是参与者观测时间；“十秒”门只验证四个首要答案在结构上的信息放置，不是人类计时结果。真人参与者 0、观测会话 0，真实设备、浏览器、低带宽网络、键盘旅程和屏幕阅读器运行均为 `NOT_EXECUTED`；生产界面实现/部署、正式 WCAG 符合性和真人可用性仍未验证，不能被机器设计合同的 `PASS` 覆盖；
- `S03 整体复审` 已冻结并解决 5 条 findings：失败指引无障碍顺序、建议/不建议与 49 个失败面的单一阶段重放、十秒结构门声明边界、后续演进下的不可变历史回执重放，以及 GitHub 双 run 暴露的 S02 前序复审门不识别已签名 S03 整体后继；独立 Oracle 60/60、定向测试 184/184、全回归 3340/3340、TaskPack 49/49、付费依赖扫描与 12/12 回滚均为 `PASS`；S03 四个 Phase 未单独上传，整体已通过 GitHub PR #69 合并到 `main`，两条 main CI 成功记录、A$0 交付门和离线 Git 历史已固化为不可变交付收据，因此才允许进入 `S04/P01`；
- `S03/P01` 至整体复审没有新增网络调研、访问平台或云账户、调用 API、clone/安装候选、执行模型、部署生产、提供真实下单能力或花费新增现金；A$300 本金、A$0 新增现金与用户唯一完成最终下单的边界保持不变，30% 月度滚动复利目标仍为待证伪、未验证且不保证的目标；
- `S04/P01` 已实现任务包唯一要求的基础设施即代码面：`infra/compose.yml`、`infra/systemd/abd.service`、`infra/config.schema.json` 与 `infra/rebuild.sh`。一条命令可从外部配置确定性生成公开部署 bundle；镜像必须使用 SHA-256 digest、禁止本 Phase build/pull，容器固定非 root、只读根目录、移除 capabilities、禁止提权、限制 CPU/内存/PID、仅监听 `127.0.0.1`，秘密只以宿主机文件路径引用且不读取、不写入仓库；候选 Oracle 61/61、定向测试 91/91、全回归 3431/3431 均为 `PASS`；
- `S04/P01` 只交付离线可重建合同，不等于已部署或 7×24 运行；其不可变签名证据现由 Phase commit 历史回放验证。`S04/P02` 已在此基础上实现 `infra/cloudflared.yml`、`access_policy.md` 与 `degraded_page.html`：Named Tunnel 模板只指向 `127.0.0.1:8080`，指标只绑定 loopback，入口以拒绝式 404 catch-all 结束；Access 合同默认拒绝，只允许唯一账户持有人的精确外部身份并强制后续验证 MFA，禁止 Everyone、通配邮箱域、Bypass 与 Service Auth；中文静态降级页会停止新建议并使旧建议失效；
- `S04/P02` 的 77/77 离线 Oracle、110/110 定向测试、3541/3541 全量回归、TaskPack 49/49、A$0 依赖扫描和 6/6 回滚均已通过。该 PASS 只证明“无需开放 OVH 业务入站端口”的配置合同与确定性回放，不证明真实可访问、7×24 或生产已上线：本 Phase 未访问 Cloudflare/OVH 账户、API、Dashboard、DNS 或主机，未创建或运行 Tunnel，未应用 Access 策略，未读取秘密，也未激活生产、提交订单或验证收益；普通全球中文页面不构成中国大陆境内加速、可用性或可达性保证，China Network 的 Enterprise 单独订阅与 ICP 前置不属于 A$0；
- `S04/P03` 已实现 `release_slots.json`、`feature_flags.json` 与可执行 `rollback.sh`：blue/green 两槽仅绑定 loopback，共享账本、证据、邮件、Outbox 与检查点固定在槽位外的 `/var/lib/abd`；候选影子模式只读共享状态，切换前停止新建议、作废旧建议、检查点并验证账本/证据完整性；未知探针、畸形开关、清单不一致、路径逃逸或账本变异全部关闭建议并 fail-closed；来源、运动、市场族和模型的小流量阶梯使用 0/100/500/2500/10000 basis points，P03 中所有 profile 均禁止开启真实建议；
- `S04/P03` 的 90/90 离线 Oracle、155/155 定向测试、3696/3696 全量回归、682/682 跨阶段签名态回归、TaskPack 49/49、A$0 依赖扫描与 16/16 回滚/故障场景均为 `PASS`。确定性演练证明成功回滚场景的冻结合成账本文件名、字节数和 SHA-256 完全不变，`899s` 与 `900s` 通过、`901s` 明确超时并保持建议关闭；这不冒充真实 OVH RTO/RPO 或生产账本验证。本 Phase 未访问主机、账户或网络，未调用 Docker/systemd，未切真实流量、未部署、未提交订单、未验证收益；生产执行继续由外部 activation record、S04 整体复审和未来运行时账本 Oracle 阻断；
- `S04/P04` 已实现 `capacity_budget.json`、`resource_shedding.json` 与 `load_baseline.json`：声明但未实机核验的 VPS-1 包络固定为 2 vCPU、4096 MiB 内存、40960 MiB 磁盘和禁用 swap；CPU、内存与磁盘桶均以整数完整分配，账本和验收证据禁止自动删除，只有有界运维日志与临时文件可自动轮转。资源状态严格按 `NORMAL → CONSTRAINED → CRITICAL → EMERGENCY` 升级，未知、缺失、负数、布尔冒充数值或超过 30 秒的遥测统一进入 `EMERGENCY`；候选槽、回填、可选 Gmail 工作与新浏览器会话先于核心完整性路径降级，任何状态都不能自动启用真实建议、真实下单、付费扩容、swap 或降低证据/数值/风险/安全/来源门；
- `S04/P04` 的 70/70 离线 Oracle、165/165 定向测试、3861/3861 全量回归、847/847 跨阶段签名态回归、TaskPack 49/49、A$0 依赖扫描与 21/21 资源边界/故障场景均为 `PASS`。365 天冻结合成 10× 设计负载先进入 `CONSTRAINED`，停止候选槽与可选写入后回到 `NORMAL`；模型使用 0 MiB swap，最终磁盘占用 32396 MiB、剩余 8564 MiB，未触及硬容量且保留至少 4096 MiB 安全余量。这只证明确定性整数预算和有界降级设计，不证明真实 OVH 容量、生产 10× 吞吐、7×24、Cloudflare 可达性、收益或上线；本 Phase 未访问 OVH/Cloudflare/Gmail/账户/API/网络，未运行 Docker/systemd/真实浏览器或真实负载，未改变 swap/磁盘、未部署、未提交订单、未花新增现金。其不可变 Phase 回执仍以 `S04/STAGE_REVIEW_READY_NOT_STARTED` 结束，中间 Phase 未单独上传 GitHub；
- `S04 整体复审` 已建立独立合同、findings、fixture、Oracle 和回滚演练。复审发现并在同一候选中关闭 6 项跨 Phase 问题：为候选影子槽补上显式 Compose profile，将 250m CPU、512 MiB 内存、0 MiB swap、单实例、`127.0.0.1:8081/8082` 和 `/var/lib/abd` 只读访问绑定到发布与容量合同；新增非 root、仅出站、前置路径 fail-closed 且经 systemd 硬化的 `abd-cloudflared.service`；用单一 Oracle 耦合 active `127.0.0.1:8080`、Tunnel/Access origin、双槽端口、资源预算和先停 shadow 的降级动作；P04 与前序 Phase 只对白名单文件允许从固定 implementation commit 精确回放，部分候选或部分签名状态继续失败关闭。候选 preflight 29/29、整体 Oracle 75/75、复审定向测试 94/94、全量回归 3958/3958、跨阶段签名态回归 944/944、TaskPack 49/49、A$0 扫描和 18/18 回滚均已通过；Stage 4 已通过 GitHub PR #79 合并到 `main`，两条 main CI、A$0 交付门和精确 Git 历史已固化为不可变交付收据，因此才允许进入 `S05/P01`；
- `S04 整体复审` 不把配置合同升级为运行事实：本地复审没有访问 OVH、Cloudflare 或 Gmail 账户/API/主机，没有读取或配置秘密，没有运行 Docker、systemd 或 `cloudflared`，没有产生真实流量或负载。OVH 7×24、全球中文可达、中国大陆加速/可达、Tunnel/Access 已应用、静态降级页已自动接线、真实 10× 吞吐、真实 RTO/RPO、磁盘容量与生产上线均保持未验证；A$300/A$0、无真实下单模块、用户唯一完成最终下单、目标不足不得放宽门和 30% 月度目标不保证的边界不变。Stage Review PASS 只会进入 `S04/GITHUB_STAGE_UPLOAD_READY`，不会激活生产或开始 S05；
- `S05/P01` 已冻结运动、联赛/竞赛、赛事、周期、盘口、选择、线和结算规则 8 类市场本体，并以显式 `UNKNOWN`、原因码、隔离动作和禁止建议状态承接歧义、未知或关系错误；`coverage_manifest.schema.json` 要求每个已观察输入恰好生成一条记录，唯一 source reference、record/object ID、可解析父关系、无环图、每个盘口至少一个选择且恰好一个结算规则，任何静默丢失、重复或越权声明均失败关闭；
- `S05/P01` 的冻结夹具仅含 9 个合成对象（8 个已知类型和 1 个显式未知），不是真实供应商或真实市场证据。独立 Oracle 52/52、定向测试 115/115、全量回归 4074/4074、TaskPack 49/49、A$0 扫描与 13/13 回滚均为 `PASS`，下一状态严格为 `S05/P02_READY_NOT_STARTED`；本 Phase 不单独上传 GitHub，须等 S05 四个 Phase 完成并整体复审后统一上传；
- `S05/P01` 只建立市场对象类型与覆盖清单 Schema，不枚举或证明“全部可观察市场”，不解决跨来源实体身份，不验证来源条款/能力、实时性、调度或静默缺口，不访问 TAB、Gmail、OVH、Cloudflare 或任何外部账户/页面/API，不执行模型、生成建议、提交订单、部署生产或验证收益；这些边界分别留给后续合同与运行时证据，30% 月度滚动复利目标继续保持未验证且不保证；
- `S05/P02` 已把 TAB、Sportsbet 与未绑定的其他可观察来源，按公开页面、静态文件、免费端点、只读登录观察和用户页面即时校验 5 种方式展开为 15 条版本化能力记录；每条记录都绑定来源事实、合同版本、必需门、失败动作与零请求预算。TAB 的屏幕抓取/第三方凭证访问、未获明确授权的 TAB Web Services/Studio，以及未有官方许可证据的 Sportsbet 自动化/API 均失败关闭；未绑定来源不得隐式继承任何能力；
- 当前 15/15 个真实来源能力全部为 `production_collection_enabled=false`、`runtime_verified=false`，这不是“来源永久不可用”，而是缺少来源特定的当前权限、许可证、身份、频率、Schema、时间与运行证据时不得采集。正向 Oracle 只使用冻结合成静态文件合同且不会执行外部动作；本 Phase 未访问 TAB、Sportsbet、Gmail、OVH、Cloudflare 或任何页面、账户/API，未观察真实市场、实现调度、生成建议、提交订单、部署或验证收益，下一状态只能是 `S05/P03_READY_NOT_STARTED`；
- `S05/P03` 已实现纯函数式 `scheduler.py`、`cadence_tests.json` 与 `rate_budget.json`：五档刷新、报价与建议时效严格绑定 Canonical Facts，恰好 24 小时、2 小时和 15 分钟采用更紧的“不利分类”；每分钟重算距离，固定时钟偏差以整数微秒判定，正负恰好 2 秒通过、超过 2 秒失败关闭；报价必须同时具备可信来源时间、观察时间和内容哈希，并以两者中更老的时间计算有效年龄，超过建议时效即不得进入建议评估；
- 当前 `S05/P03` 的 15/15 个真实来源频率预算仍为 0 且禁用，未从 P02 推断任何权限或运行能力。唯一正向计划使用冻结合成来源，指数退避无随机抖动且只生成下一到期时间，不执行网络、进程、采集、模型、建议、下单或部署；P04 静默缺口审计保持未启动，30% 月度目标仍未验证、不保证且不能放宽来源、时效、证据、数值、风险或安全门；
- `S05/P04` 已建立 `coverage_dashboard.json` 与纯标准库 `silent_gap_oracle.py`：覆盖宇宙严格来自 P02 已签名的 3 个 provider × 5 种访问模式，共 15 个唯一能力单元；每个单元恰好一条记录，缺失、重复、身份错配、未知状态、缺少原因/恢复动作/Owner、伪造运行门或建议资格都会失败关闭。当前矩阵为 2 个待解析、4 个不可建议、2 个降级、7 个未知，15/15 均为显式缺口，静默缺口为 0；
- 当前 `S05/P04` 的 PASS 只证明固定 provider-mode 合同宇宙内不存在被吞掉的缺口，并且每个显式缺口都有原因、恢复动作和 Owner；它不证明已枚举全部真实市场，不证明任何真实来源许可、账户、页面、API、运行采集、时效、生产覆盖或上线。生产覆盖仍为 0/15，所有真实能力与频率预算继续禁用，未访问网络/TAB/Sportsbet/Gmail/OVH/Cloudflare，未执行模型、生成建议、提交订单、部署或验证收益；下一状态只能是 `S05/STAGE_REVIEW_READY_NOT_STARTED`，须在下一独立 Run 完成整个 S05 复审和整改后才可统一上传 GitHub；
- `S01/P01` 至 `S01/P04` 只冻结客户体验、疑问、需求、范围、指标、经济和证伪合同，不证明产品已实现、部署、接入账户或验证收益；四个中间 Phase 均未单独上传 GitHub；
- `S00/P02` 冻结的是授权规则，不证明 OVH、Cloudflare、GitHub、Gmail 或任何平台凭证/能力当前可用；
- `S00/P03` 只证明当前声明依赖的 ABD 新增现金成本为 A$0、付费接口不在关键路径；既有 OVH/账户总成本、外部能力与免费额度余量仍未知；
- `S00/P04` 冻结 Gmail 可选 consent、精确 scope、方法白名单和降级状态机；本 phase 未生成 OAuth 链接、未访问账户、未取得或保存 token、未调用 Gmail API，Gmail 仍为 `NOT_CONNECTED / UNVERIFIED / NOT_READY`；
- 当前禁止真实下单，30% 月度滚动复利只是待证伪和长期验证的目标，不是收益保证。

当前 `S03 整体复审` 的定向与全回归验证命令：

`S02` 的远端交付前置和 `S03/P01` 至 `S03/P04` 的签名证据均由不可变收据与离线 Git 历史重放；以下命令只列 S03 整体复审的新增验证。

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S03/stage_review_test.py --junitxml=machine/evidence/S03/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S03/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S03/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S03 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S04/P04` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S04/P04_test.py --junitxml=machine/evidence/S04/P04/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/P04/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S04/P04/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/P04/full_regression.xml
uv run --frozen --python 3.12 python -m pytest -q tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/P01_test.py tests/S04/P02_test.py tests/S04/P03_test.py tests/S04/P04_test.py --junitxml=machine/evidence/S04/P04/signed_state_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/P04/signed_state_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S04-P04 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S04 整体复审` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S04/stage_review_test.py --junitxml=machine/evidence/S04/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S04/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/full_regression.xml
uv run --frozen --python 3.12 python -m pytest -q tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/P01_test.py tests/S04/P02_test.py tests/S04/P03_test.py tests/S04/P04_test.py tests/S04/stage_review_test.py --junitxml=machine/evidence/S04/STAGE_REVIEW/signed_state_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S04/STAGE_REVIEW/signed_state_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract STAGE-REVIEW-S04 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S05/P01` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S05/P01_test.py --junitxml=machine/evidence/S05/P01/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P01/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P01/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P01/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P01 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S05/P02` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S05/P02_test.py --junitxml=machine/evidence/S05/P02/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py --junitxml=machine/evidence/S05/P02/signed_state_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/signed_state_regression.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P02/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P02/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P02 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S05/P03` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python -m pytest -q tests/S05/P03_test.py --junitxml=machine/evidence/S05/P03/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py tests/S05/P03_test.py --junitxml=machine/evidence/S05/P03/signed_state_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/signed_state_regression.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P03/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P03/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P03 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

当前 `S05/P04` 的验证与签署命令：

```bash
uv run --frozen --python 3.12 python machine/tools/scan_paid_dependencies.py
uv run --frozen --python 3.12 python machine/tools/validate_pack.py
uv run --frozen --python 3.12 python silent_gap_oracle.py coverage_dashboard.json
uv run --frozen --python 3.12 python -m pytest -q tests/S05/P04_test.py --junitxml=machine/evidence/S05/P04/pytest.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P04/pytest.xml
uv run --frozen --python 3.12 python -m pytest -q tests/S03/P02_test.py tests/S03/P03_test.py tests/S03/P04_test.py tests/S03/stage_review_test.py tests/S04/stage_review_test.py tests/S05/P01_test.py tests/S05/P02_test.py tests/S05/P03_test.py tests/S05/P04_test.py --junitxml=machine/evidence/S05/P04/signed_state_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P04/signed_state_regression.xml
uv run --frozen --python 3.12 python -m pytest -q --junitxml=machine/evidence/S05/P04/full_regression.xml
uv run --frozen --python 3.12 python machine/tools/normalize_junit.py machine/evidence/S05/P04/full_regression.xml
uv run --frozen --python 3.12 python -m abd_acceptance --contract AC-S05-P04 --evidence machine/evidence
uv run --frozen --python 3.12 python machine/tools/update_artifact_manifest.py
```

## 交付

- `文档/`：严格7份人类平面文档；
- `machine/facts/`：Canonical Facts、参数、需求、验收、任务图、追踪、研究、安全和发布真源；
- `machine/schemas/`：机器合同Schema；
- `machine/tools/`：文档重生和任务包校验；
- `machine/tests/fixtures/`：数值、调度和邮件安全边界夹具；
- `machine/evidence/`：校验、追踪、路线图、清单和证据索引；
- `skill/`：完善后的Product-Design-Taskpack Skill；
- `PURSUE_GOAL_PROMPT.txt`：开发线程持续目标；
- `VERSION`：精确版本。

## 运行校验

```bash
python machine/tools/render_human.py
python machine/tools/validate_pack.py
```

通过后检查：

```text
machine/evidence/validation_report.json
machine/evidence/SHA256SUMS
```

## 关键边界

- 系统只分析和建议，不提交真实订单；
- 用户正常只完成最终下单；
- OVH全天候主运行，Cloudflare全球中文访问；
- 新增现金预算A$0；
- 所有距开始>24小时事件每30分钟刷新；
- Gmail邮件每15分钟确定性归档，验证后移入垃圾箱，Codex每天审计；
- 权威数值使用十进制定点，±0.0001和不利赔率跳动翻转即不建议；
- 30%月复利是目标、容量、证伪和长期验证合同，不是随机收益保证。
