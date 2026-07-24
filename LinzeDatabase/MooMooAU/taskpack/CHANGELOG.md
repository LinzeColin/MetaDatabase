# Taskpack Changelog

## 1.0.13 — 2026-07-24

固化 T0703 第五个 exact-main attempt 的 `MUTATION_FAILED` 结果，并只授权一个零新增写入
reconciliation 候选。

- 绑定 PR #106、main `c860f388…`、workflow run `30072484529`、authority PASS、M3 FAILED、
  identity cleanup PASS 与 rerun 0；
- 后验聚合只读核验观察到 private head 改变、一个可恢复 Processed lineage、
  processed-current `ZERO → ONE` 与 Gmail Trash aggregate 增加 1；这些聚合不证明 exact-source
  attribution，也不证明更细 mutation subreason；
- 全邮箱 metadata 筛选必须得到唯一 verified、已在 Trash、且 opaque source ID 存在该预先加密
  processed-current pointer 的候选；零或多个匹配均 fail closed；
- 对唯一候选重复 Canonical Raw/Processed 规划、Raw 与 Processed remote recovery 和第二次身份
  验证，完全跳过 Raw/Processed commit saga，且不调用 Gmail mutation transport；
- 本次 Run Contract 的 Gmail mutation、Raw ciphertext creation 与 Processed write budget均为 0；
- 五个失败 head 均禁止 rerun/redispatch；只允许一份新 exact candidate main 交付和一次
  attempt-1 zero-write dispatch；T0704、Timeline、GA、schedule 与最终发布继续为 0/未授权。

## 1.0.12 — 2026-07-24

固化 T0703 第四个 exact-main attempt 在 `AGGREGATE_GATE` 的零观察副作用失败，并只授权一个
SAFE_DEFERRED 聚合恢复候选。

- 绑定 PR #104、main `b922219f…`、workflow run `30068892160`、authority PASS、M3 FAILED、
  identity cleanup PASS 与 rerun 0；
- 后验只读核验观察到 private commit 0、Processed write 0、Gmail Trash 新增消息 0、
  source/Timeline/schedule mutation 0；
- 公开输出只证明 `AGGREGATE_GATE`，未提供 aggregate failure class；不声称聚合日志未证明的
  精确线上根因；
- 静态契约验证并修复空 classification/parser registry 下隔离附件可能错误产生 `BLOCKED` 的顺序
  冲突，使其显式生成可恢复的 `SAFE_DEFERRED` Processed；active parser profile 仍 hard quarantine；
- 新增封闭 `ProtectedM3AggregateFailureClass`，后续 aggregate failure 只输出固定枚举；
- 四个失败 head 均禁止 rerun/redispatch；只允许一份新 exact candidate main 交付和一次
  attempt-1 Budget-1 dispatch；T0704、Timeline、GA、schedule 与最终发布继续为 0/未授权。

## 1.0.11 — 2026-07-24

固化 T0703 第三个 exact-main attempt 的 `RESPONSE_SCOPE_REJECTED` 零观察副作用失败，并只授权
一个遵循官方 GitHub token 响应契约的新恢复候选。

- 绑定 PR #103、main `bc0bfb3b…`、workflow run `30066295809`、authority PASS、M3 FAILED、
  identity cleanup PASS 与 rerun 0；
- 后验只读核验观察到 private commit 0、MooMooAU 路径写入 0、Gmail Trash 新增消息 0、
  source/Timeline/schedule mutation 0；
- 固定官方 GitHub OpenAPI commit `5c88ff6b…`：installation-token 响应只强制 `token` 与
  `expires_at`，scope 回显均为可选；
- 可选 repository 回显缺失时，使用 installation token 做有界精确仓库范围探测；回显存在时仍须
  精确匹配目标 Repository ID 与最小权限；
- token 一小时 TTL 改以有界 GitHub `Date` 响应头为参考；Date 漂移或 TTL 超限均 fail closed；
- 三个失败 head 均禁止 rerun/redispatch；只允许一份新 exact candidate main 交付和一次
  attempt-1 Budget-1 dispatch；T0704、Timeline、GA、schedule 与最终发布继续为 0/未授权。

## 1.0.10 — 2026-07-24

固化 T0703 第二个 exact-main attempt 的零观察副作用失败，并在 Owner 确认 App 安装与 private 仓
链接后只授权一个全新恢复候选。

- 绑定 PR #102、main `9b15c4d5…`、workflow run `30063841144`、authority PASS、M3 FAILED、
  identity cleanup PASS 与 rerun 0；
- 公开失败边界为 `GITHUB_APP_TOKEN`；旧 M3 v1 未输出安全 installation-token failure class，
  因此不声称更精确根因；
- 后验只读核验观察到 private commit 0、MooMooAU 路径写入 0、Gmail Trash 新增消息 0、
  source/Timeline/schedule mutation 0；
- Owner 随后确认 MooMooAU GitHub App 已安装并链接唯一 private 数据仓；
- M3 现与 T0702 一样只保留封闭 `InstallationTokenFailureClass`；公开 payload 不含 App、
  installation、Secret、邮箱字段或 private 仓标识；
- 两个失败 head 均禁止 rerun/redispatch；只允许一份新 exact candidate main 交付和一次
  attempt-1 Budget-1 dispatch；T0704、Timeline、GA、schedule 与最终发布继续为 0/未授权。

## 1.0.9 — 2026-07-24

固化 T0703 首次 protected M3 的零观察副作用失败，并只授权一个新修复候选。

- 绑定 PR #101、main `f747ddcd…`、workflow run `30060804854`、authority PASS、M3 FAILED、
  identity cleanup PASS 与 rerun 0；
- 后验只读核验观察到 private 仓新增 commit 0、Processed write 0、Gmail Trash 新增消息 0、
  source/Timeline/schedule mutation 0；公开输出未声称精确根因；
- 将 T0702 已证明安全的逐消息 `MessageMetadataUnverifiable` quarantine 对齐到 M3，下一合法
  candidate 不再被单条内容安全 metadata 不可用阻断；
- authentication、authorization、transport、content boundary、global discovery、Raw/Processed
  recovery 与 Trash 失败仍整次 fail closed；
- 新增封闭 M3 phase taxonomy；公开失败 payload 不接收异常对象、动态值、邮箱字段、Secret 或
  private 仓标识；
- Run Contract 禁止失败 head rerun/redispatch，只允许一份新 exact candidate main 交付和一次
  attempt-1 Budget-1 dispatch；T0704、Timeline、GA、schedule 与最终发布继续为 0/未授权。

## 1.0.8 — 2026-07-24

在 T0702 protected PASS 后仅授权 T0703 Budget-1 first attempt，不改变产品契约。

- 当前 Run Contract 固定一份受控 main 交付、一次 protected dispatch、rerun 0、full Raw read 1、
  Processed write 1、精确 source-message Trash 1，T0704/Timeline/schedule/final publication 0；
- 复用已验证的 `moomooau-beta` Environment 与六项 protected value，新增两项公开安全空 processing
  registry；
- classification/parser registry 必须同时 ACTIVE 且匹配，或同时为空；空注册表只能生成加密
  `SAFE_DEFERRED`，不得猜测分类或 parser profile；
- Raw 与 Processed age ciphertext 均须从唯一 private remote 恢复后，再次验证同一来源并仅调用
  `users.messages.trash`；
- protected T0703 receipt 尚未产生，因此 T0703/S7AC-003 与最终 Acceptance 保持 NOT_RUN/BLOCKED。

## 1.0.7 — 2026-07-24

只补齐 T0703 受保护入口，不执行或授权 M3，不改变产品契约。

- 新增独立 `ProtectedM3Bootstrap`，将 verified Raw、Processed complete/safe-deferred、Raw 与
  Processed 远端恢复、第二次发件人验证及唯一 exact-message Trash 收敛为 Budget 1；
- 新增 manual、main-only、owner/actor-bound、GitHub-hosted、attempt-1 的 M3 Workflow，权限仅为
  `contents: read`，Secret 引用精确限制为八个名称；
- 无 Secret job 绑定 exact main SHA、T0702 PASS receipt、同树 M3 gate 与当前 Run Contract；
- 当前 `m3_authorized=false`，所以 Workflow 默认禁用并在 Secret 读取前停止；
- 合成端到端验证 Processed 恢复先于 exact Trash、age ciphertext-only 写入、零附带 Gmail
  mutation 与临时身份清理；
- 真实 Gmail、私有数据仓、Processed、M3、Timeline、dispatch 与发布效果均为零；T0702/S7AC-002
  既有 PASS 不变，T0703、最终 Acceptance、生产健康、Stage 7 完成与最终发布仍未通过。

## 1.0.6 — 2026-07-23

按 Owner 选择的方案 2 只解决 RMD-06 云执行前置，不改变产品契约或授予生产权限。

- Governance 保持私有，认证收敛为单仓只读 Deploy Key；
- 凭据只允许进入 pinned `actions/checkout` 的 `ssh-key` 输入，不进入 env、shell 或项目 Python；
- 8 个依赖 Governance 的 Workflow 在 checkout 前拒绝 fork PR，并继续禁止 `pull_request_target`；
- 修复 `runner.temp` 在 job-level `env` 的无效 context，新增全 MooMooAU Workflow 解析门；
- 首轮 clean-clone 预检暴露并修复 RMD-05 旧 Git object 隐式依赖，关闭前序改由不可变 v1.0.5
  Manifest 与 assurance provenance 验证；
- 为 Stage 1 parser 精确固定 `PyYAML==6.0.3`，并将 Stage 3 所需 `pikepdf==10.10.0` 纳入既有
  累计 hash lock、80-component SBOM、advisory 与容器验证面；
- 第三轮 depth-1 预检后，将 v1.0.6 状态构建的 composition 检查分为历史累计 Job 的 hash-bound
  静态层与 Stage 7 完整依赖 Job 的真实 CLI 层，不改 production execution path；
- Stage 6 在精确 v1.0.5 Manifest 与 82 个不可变 authority 文件通过后，以 portable 方式验证当前
  receipt bundle；旧 RMD-05 Git object 仍不成为 clean checkout 隐式依赖；
- 对 Stage 5 校验器中的固定 production Workflow SHA-256 增加单行 entropy allowlist，扫描范围、
  检测器与其他发现处理保持不变；
- 第四轮预检后，Stage 6 Workflow 改为调用既有结构化 Secret gate：不可变 receipt/provenance JSON
  由 JSON 解析与显式高风险凭据模式验证，其余范围继续由 `detect-secrets` 扫描；Stage 7 只精确
  排除四个公开前序 Manifest SHA-256，不增加宽泛凭据值排除；
- “no-Secret”修订为“零生产 Secret + 唯一只读依赖凭据”；
- 第五轮精确生成的 9 个 GitHub-hosted 非生产 Workflow 全部成功，随后删除远端候选分支；没有 PR、
  merge、部署或发布；
- 新增 T0702 唯一手动 main-only protected Beta Workflow 与显式 entrypoint，绑定控制仓/owner/actor、
  expected SHA、GitHub-hosted 首次 run attempt、同树 Alpha、protected Environment 和六项精确
  Secret 名；
- Beta 路径仅允许 verified Raw age commit/recovery；Gmail mutation、Parser、M3、Processed、Timeline
  与 schedule 权限为零，并以本地 task oracle 固化；
- protected Environment、真实输入、私有数据仓与 GitHub App 尚未配置或证实，且中间上传顺序冲突
  未解决，因此真实 Beta/S7AC-002 继续 `BLOCKED/NOT_RUN`；
- Owner 一次性授权后，`moomooau-beta` 已收敛为无 reviewer、`main`-only，六项精确 Environment
  Secret 已配置；唯一私有数据仓、单仓最小权限 GitHub App、cloud-only age identity、预算 1、
  fresh-capacity config、Gmail OAuth 与 protected sender registry 均已独立核验；
- 真实 metadata-only 发现确认 Gmail 默认 metadata 响应仍可能携带 `snippet`，因此 Beta 请求现强制
  exact partial-response fields 并继续拒绝任何内容派生字段；sender verifier 同时按 RFC 8601 接受
  `header.i`，且对同一 DKIM 结果中出现的全部 `header.d`/`header.i` identity fail closed；
- 经唯一授权的 PR #88 已合并到 `main`；该受控 Beta 交付不是最终发布，普通 main CI 全绿；
- 唯一 first-attempt protected workflow 已执行：同树 Alpha PASS，Beta 返回
  `PROTECTED_BETA_RUN_FAILED`，identity tmpfs cleanup PASS；未 rerun；
- 运行后唯一私有数据仓仍为 64-byte 单文件、单 commit、零 release 的 bootstrap 基线，首个远端
  Raw commit 未发生；verified full Raw read 因 aggregate-only 日志只能记为
  `UNDETERMINED_WITHIN_BUDGET_ONE`，不得伪造为 0；
- Gmail mutation、M3、Processed、Timeline、schedule、production Workflow 与最终发布仍为 0；
  T0702/S7AC-002、生产健康与最终 Acceptance 均未通过；
- 新增精确 schema-bound 失败 receipt，并把唯一状态、Stage 7 aggregate、Acceptance、Governance
  facts/七文档、provenance 与 Manifest 收敛到 `BLOCKED_PROTECTED_BETA_FAILED`；本轮停止，不进行
  第二次交付、dispatch、rerun 或 M3；
- 后续纯本地 Stage 7 repair 新增 19 项固定 public-safe failure phase、唯一 reason-code mapping
  与拒绝额外字段/错配的 exact JSON Schema；renderer 不接收异常对象或动态 protected 值；
- 合成 phase probes 覆盖 context、bootstrap、Raw runtime、recovery、aggregate 与 cleanup，
  repair Run Contract 的远端、Secret、Gmail、私有仓、M3 与发布预算全部为 0；该 repair run
  当时未上传，历史失败根因仍未知，T0702/S7AC-002 仍为 `BLOCKED`；
- 按 Owner 最新指令移除 M3 七天与 Blue-Green 十四天的固定日历等待；两阶段分别以一次有界受保护
  运行中的确定性恢复、Mutation、Parser 比较、Full Reconcile 与单一 Timeline 证据判定，前序和
  安全门保持 fail closed，GA 仍须真实观察一次 04:30 Australia/Sydney 调度。
- Owner 在历史一次性 T0702 授权消费后进一步授权受控完成 Stage 7；新增 completion Run Contract，
  允许已验证 repair 的 PR/merge 与 exact-main-SHA-bound serial new first-attempt dispatch，禁止
  GitHub rerun，Beta 继续预算 1/零 Gmail mutation，M3 继续以真实 Beta PASS 为硬前序。
- 通过 PR #92–#95 交付公开安全诊断并在四个互异 exact-main SHA 各执行一次 workflow attempt 1；
  固定结果依次收敛为 `GITHUB_APP_TOKEN`、`INSTALLATION_NOT_FOUND`、
  `INSTALLATION_DISCOVERY_REJECTED`、`INSTALLATION_ZERO`，每次 Alpha 与 identity cleanup PASS，
  Raw/Gmail mutation/M3/Processed/Timeline/schedule 均为 0，GitHub rerun 为 0。
- 新增 schema-bound `attempt-ledger.json`，绑定历史首次运行与四次诊断运行；最新事实仅证明现有
  GitHub App 的 installation 列表为空，不声称 T0702、生产健康或最终 Acceptance 通过。
- PR #96 以 35 success、5 expected skip、0 failure 合并账本与派生状态；精确 merge SHA 的新
  workflow attempt 1 再次得到 `GITHUB_APP_TOKEN / INSTALLATION_ZERO`，Alpha 与 identity
  cleanup PASS，Raw/Gmail mutation/M3/Processed/Timeline/schedule/rerun 继续为 0。
- 后续 first-attempt 序列先后 fail closed 于 GitHub App installation selection、token request、
  response scope 与 Gmail metadata verification；修正 response scope 后，单封 404/结构不完整
  metadata 被收敛为 typed、bounded quarantine，其他内容/身份/权限/服务异常仍整次 fail closed。
- v2 ledger 现精确区分 1 次 Secret 前 context 拒绝与 11 次 protected first attempt；最终
  exact-main attempt 的 Alpha、Raw-only Beta 与 identity cleanup 均 PASS，GitHub rerun 为 0。
- 最终公开安全证据为 verified within configured budget、Raw remote recovery 100%、private
  namespace 非零 age ciphertext only，以及 Gmail mutation/M3/Processed/Timeline/schedule 为 0；
  不披露精确邮箱计数、private 对象数量或仓标识。
- T0702/S7AC-002 已通过；M3 前序满足但当前 Owner 范围停在 M3 前。生产、最终 Acceptance、
  Stage 7 完成与最终发布仍为 false。

## 1.0.5 — 2026-07-22

按 v1.0.4 已冻结的复审修复顺序完成 RMD-05，不改变产品契约或冒充受保护/生产证据。

- 以 same-tree Git anchor 固定候选、19-command 执行回执与不可变 request；
- 两个模型家族各保留 18 次有序复审、共 36 个互异 Codex task ID，最终回复独立 PASS；
- 保留所有 adverse、rejected 与 superseded 历史，并关闭至 `RMD05-CLOSURE-012` 的完整 finding 集；
- Stage 6 evidence 升为 candidate/receipt-bound v2，Acceptance 仍为 0/34 final PASS；
- 唯一状态、Governance facts、七文档、provenance 与 package manifest 均确定性生成；
- 真实 Gmail、私有仓、Secret、受保护 Oracle、生产、部署和发布计数保持 0，下一 run 仅进入 RMD-06。

## 1.0.4 — 2026-07-22

按 v1.0.3 已冻结的复审修复顺序完成 RMD-04，不改变产品契约或冒充生产证据。

- 新增唯一 fail-closed production composition 和显式 contract-only/protected CLI；
- 将 04:30 Sydney 的最后成功日期写入 age 加密远程 checkpoint v2，并兼容读取 v1；
- 将官方 age Timeline crypto 与远程首次导入时间恢复从测试替身提升为生产源码适配器；
- 生产 Workflow 绑定 stage6 hash lock、固定 age 下载哈希、八个精确 Secret 名和完整 GA runner；
- 合成 Gmail/GitHub HTTP 端到端证明远程恢复先于 exact message Trash，单一 Timeline 最大值为 1；
- 真实/受保护/生产/发布计数保持 0，下一 run 仅进入 RMD-05 assurance provenance。

## 1.0.3 — 2026-07-22

按 v1.0.2 已冻结的复审修复顺序完成 RMD-03，不改变产品语义。

- S3–S6 validator CLI 新增显式 `--cumulative-final`，只退休已由后续累计层接管的 scope check；
- 无参数历史阶段模式仍确定性 `BLOCKED`，所有生产权限、外部效果和禁止项检查保持 fail closed；
- S3–S6 GitHub workflows 显式使用累计最终树模式；
- 新增离线只读 Workflow command matrix，逐项回放 4 个累计 PASS 与 4 个历史负向控制；
- 本地矩阵不替代远端 CI、受保护 Oracle 或生产运行；下一 run 仅进入 RMD-04 生产 composition。

## 1.0.2 — 2026-07-22

Owner 选择方案 1，授权建立不改变产品语义的基线保真继任版本。

- 原样继承 v1.0.1 的 34 RQ、34 AC、58-task DAG、追踪矩阵、Kill Criteria 与十条产品不变量；
- 保留 v1.0.1 Manifest 字节不变，并用固定哈希校验其历史身份；
- 让 S0 使用既有语义、S1–S7 使用各自 stage schema 和局部 acceptance contract 验证 evidence；
- 建立 `machine/status/latest.json` 作为唯一当前跨维度状态权威，明确分离 evidence 完整性、本地机制、
  正式任务、受保护 Oracle、最终验收、生产就绪与发布；
- 当前只证明本地/合成机制，不执行或伪造受保护 Oracle、生产运行、远端写入或 GitHub 上传；
- RMD-02 完成后下一 run 仅进入 RMD-03 累计 CI 修复。

## 1.0.1 — 2026-07-20

Owner 已明确授权基线保真修复。Pursuing Goal、S0–S7 范围和产品安全边界不变。

- 新增 S0AC-001…S0AC-007，分离 Stage 0 局部门与最终 AC-*；
- 以只读 Manifest 校验替代会自修改证据的原验证器；
- 以可验证串行替换和零资产修复态替代平台不支持的原子声明；
- 明确 04:30 是 GitHub 时区感知调度目标而非精确启动 SLA，并冻结延迟/丢弃后的幂等补偿；
- 明确 age 密文具有安全随机性，Timeline 无变化 Oracle 使用 Snapshot Root 与解密验证后的明文摘要；
- 通过 pinned external checkout 消费共享 Governance，不复制框架；
- 私有仓名称移出公开树，使用受保护 immutable Repository ID；
- 未经一手证据确认的发件人候选保持 `UNKNOWN`；
- 本地 v1.0.0 审计历史永久禁止 push，最终发布必须使用干净快照历史。

## 1.0.0 — 2026-07-19

用户提供的原始设计任务包。其哈希、完整性与已发现问题保存在 `SOURCE_PROVENANCE.json`。
