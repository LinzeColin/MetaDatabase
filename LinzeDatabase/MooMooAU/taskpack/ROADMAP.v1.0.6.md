# MooMooAU Archive Roadmap v1.0.6

本版本是 v1.0.5 的基线保真控制继任。v1.0.1 冻结的 Pursuing Goal、S0–S7、34 RQ、34 AC、
58-task DAG、Kill Criteria 与十条不变量全部继续有效。

## 不变的产品契约

| 契约 | 数量或身份 | SHA-256 |
|---|---:|---|
| Requirements | 34 | `ea1c5ec0371576b1852cc23d5836eaf21b044a577ee6c6c1a92dddc3923bea27` |
| Acceptance Contracts | 34 | `3115ea47f01549218c817845554dc32b019a894708c4ac311e99249bcabf95bb` |
| Traceability Matrix | 34 RQ ↔ 34 AC ↔ 58 tasks | `263250bceb42d623c4491b99665dff3d1ba08e78f4e43a4fde74380a5e28abf2` |
| Task DAG | 58 tasks | `72785605390a31c8dbb0a5d349cf81418b158f7714e46fe8e7f8e4b113f318d9` |
| Kill Criteria | 原样继承 | `2a0494577382d1529721b05c6b03f874787f8c8deb5dbd4a56895624573f25dc` |
| Canonical Facts | 十条不变量 | `27110e8e6d8d337474eefa29f51d5bf294061c90dfebac2e0d898268dce96bf2` |
| v1.0.5 Manifest | 不可变直接前序 | `f99413b9c1fb67369ba3039a7acfeb437004d1aad8cb54dc3697f87f38e35cb3` |

## RMD-06 云执行前置闭包

目标仅为建立可运行的 GitHub-hosted 验证前置：

- 修复 GitHub expression context；
- 为私有 Governance 使用单仓只读 Deploy Key；
- 凭据仅供 pinned `actions/checkout` 使用；
- fork PR 在凭据 checkout 前 fail closed；
- clean checkout 对已关闭 RMD-05 前序只依赖不可变 Manifest，不依赖候选分支不可达的旧 Git object；
- 普通 CI 的 parser 与 Stage 3 PDF runtime 依赖必须完整进入精确 pin、hash lock、SBOM 和审计面；
- 历史累计 Job 对 v1.0.6 使用 hash-bound composition 静态验证，Stage 7 完整依赖 Job 继续执行
  contract-only CLI，二者不得互相冒充；
- Stage 6 先验证 v1.0.5 Manifest 与完整不可变 authority set，再验证当前 receipt bundle；depth-1
  checkout 不得因缺少已关闭前序的旧 Git object 而改变证据结论；
- Stage 6 的不可变结构化 receipt/provenance JSON 使用 JSON 解析与显式高风险凭据模式验证，其余
  代码/契约范围继续执行 `detect-secrets`；固定非 Secret SHA-256 只允许精确值 allowlist，不允许
  宽泛凭据值排除；
- 普通 CI 的生产/Gmail/数据仓 Secret 读取保持零；
- 不执行生产、Gmail mutation、私有数据仓写入、部署或最终发布。

本版本不把依赖凭据读取解释为生产 Secret 读取，也不把 GitHub-hosted CI 解释为 protected Oracle。
任何 Workflow syntax、Governance pin、Secret 边界、fork policy、package、publication 或 cumulative gate
失败都停止 RMD-06。

第五轮受控候选提交 `2e1dda85a9bc85fb656eb6b6abb8f775bfef9292` 已让精确生成的 9 个
GitHub-hosted 非生产 Workflow 全部 `completed/success`；候选远端分支随后删除，没有 PR、merge、
部署或发布。该结果只关闭云执行前置，不满足任何 protected Oracle。

## T0702 Beta 当前 Run Contract

本轮只允许把 T0702/S7AC-002 的受保护 Raw-only 入口做到本地可部署和可验证：

- 唯一入口为 `.github/workflows/moomooau-beta.yml`，只接受 owner 在 `main` 上手动
  `workflow_dispatch`；
- 先绑定控制仓/owner/actor 数字 ID、expected commit、Workflow ref、GitHub-hosted runner、
  首次 run attempt、受保护 `moomooau-beta` Environment 与同树 Alpha gate，再读取任何 Beta Secret；
- 执行步只接受六个精确名称：Beta config、sender registry、GitHub App private key、age identity、
  opaque ID key 与 Gmail OAuth；
- 只允许 Raw archive 与远端恢复；Gmail mutation、Parser、M3、Processed 与 Timeline 均为零；
- 成功必须观测 1..显式正整数预算个真实已验证消息且远端恢复 100%；公开输出仅为 bucket、零值计数
  与 gate 布尔值，不公开精确预算或精确邮箱/恢复计数；
- 代码就绪不等于真实 Beta。Environment、六个值、消息预算、verified registry、唯一私有数据仓和
  GitHub App installation 未配置或未证实时，Oracle 必须保持 `NOT_RUN`。

Owner 已于 2026-07-23 仅为 T0702 解除一次上述顺序冲突：允许一次受控 PR/merge 到 `main` 和一次
budget-one protected Raw-only dispatch，且 `moomooau-beta` 不设人工 reviewer。该例外不授权第二次
交付、rerun、Gmail mutation、M3、Processed、Timeline、schedule 或最终发布；任一前置无法独立核验
即停止。

## 后续顺序

1. 只读 Governance Deploy Key 与 GitHub-hosted 非生产预检已完成并关闭临时远端候选；
2. T0702 protected Raw-only 入口完成本地机制验证，但真实 Beta Oracle 保持 `NOT_RUN`；
3. 按一次性 Owner 授权配置 no-reviewer/main-only Environment、六项 Secret、预算 1、verified
   registry、唯一私有仓与单仓最小权限 GitHub App，再从精确 merged SHA dispatch 一次；
4. Beta 真实 Oracle 全绿后，RMD-06 才可按 M3 → Timeline Blue-Green → GA → Recovery → 最终 AC
   的既定顺序继续；每个未知或失败结果立即停止；
5. RMD-06 完成后进入 RMD-07 最终复审与干净一次性发布。
