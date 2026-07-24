# MooMooAU Archive 开发任务包 v1.0.6

- Package ID：`MMAU-ARCHIVE-TP-2026-07-23-V1.0.6`
- 授权依据：Owner 选择方案 2，Governance 保持私有，并为 MetaDatabase 配置单仓只读 Deploy Key
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：原样继承 v1.0.1 的 34 RQ、34 AC、58-task DAG 与十条不变量
- 直接前序：v1.0.5 Manifest 字节不可变；v1.0.4、v1.0.3、v1.0.2 与 v1.0.1 继续固定
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`CONTROLLED_BETA_DELIVERY_NOT_FINAL`

## 本版本只解决的 RMD-06 前置阻塞

1. 修复四个 Workflow 在 job-level `env` 使用不可用 `runner.temp` context 导致的零 Job 失败；
2. 私有 Governance 只允许通过 `MOOMOOAU_GOVERNANCE_DEPLOY_KEY` 读取；
3. 该凭据只能进入 `actions/checkout` 的 `ssh-key` 输入，不得进入 env、shell 或项目 Python；
4. Deploy Key 只绑定 `LinzeColin/Governance`，写权限关闭，checkout 后不保留凭据；
5. fork pull request 必须在 Governance checkout 前显式失败；禁止 `pull_request_target`；
6. “no-Secret”口径修订为“零生产 Secret + 唯一只读依赖凭据”，真实 Gmail、数据仓与生产 Secret
   仍不得用于本地或普通 CI；
7. 私钥材料不得进入代码树、Manifest、日志、模型上下文或本地持久化。
8. clean checkout 不得依赖本地共享 Git object database 中的旧 RMD-05 anchor；关闭的直接前序只通过
   精确 v1.0.5 Manifest 和完整 assurance provenance 验证；
9. Stage 1 Workflow parser 的 `PyYAML` 必须精确固定，Stage 3 PDF runtime 的 `pikepdf` 与
   `Pillow` 必须进入其既有累计 hash lock、SBOM、advisory 和容器验证面；
10. 以上三项由首轮受控候选分支预检暴露，仅属于 RMD-06 Workflow 可执行性修复，不改变产品契约、
    protected Oracle、生产或发布口径。
11. 后续 depth-1 预检继续要求：v1.0.6 状态构建在历史累计 Job 中只执行 hash-bound composition
    静态验证，完整依赖的 Stage 7 仍必须执行真实 contract-only CLI；Stage 6 在独立验证精确 v1.0.5
    Manifest 与 82 个不可变权威文件后，只对当前 candidate bundle 做无旧 Git object 的结构绑定；
    Stage 6 的不可变结构化 receipt/provenance JSON 由 JSON 解析与显式高风险凭据模式验证，其余范围
    继续执行 `detect-secrets`；Stage 5 固定 Workflow SHA-256 与 Stage 7 四个公开前序 Manifest
    SHA-256 只允许精确值 allowlist，不得增加宽泛凭据值排除。
12. 这些后续修复只消除第三轮 GitHub-hosted 非生产预检暴露的环境误耦合与确定性误报，不改变
    production composition、RMD-05 evidence、受保护 Oracle、最终 Acceptance 或发布语义。
13. 第五轮精确生成的 9 个 GitHub-hosted 非生产 Workflow 已全部成功；远端候选分支已删除，未创建
    PR、未 merge、未部署或发布。该结果关闭云执行前置，但不满足 protected Oracle。
14. T0702 新增唯一手动、main-only、owner-bound、expected-SHA-bound、GitHub-hosted-first-attempt 的
    `.github/workflows/moomooau-beta.yml` 与显式 protected entrypoint；执行步只引用六个精确 Beta
    Secret 名称，并在读取前验证同树 Alpha 与 GitHub 上下文。
15. 该入口只装配 Raw archive/recovery，Gmail mutation、Parser、M3、Processed、Timeline、schedule
    与控制仓写权限全部为零；本地合成测试不能替代真实 Beta。
16. Owner 授权后，`moomooau-beta`、六项 Secret、预算 1、verified registry、唯一私有数据仓和
    单仓最小权限 GitHub App 已独立核验；一次受控 PR/merge 和一次 first-attempt dispatch 已用尽。
    同树 Alpha PASS，但 protected Beta 在首个远端 Raw commit 前失败，精确内部根因因
    aggregate-only logging 不可判定；T0702/S7AC-002 继续 `BLOCKED`，禁止本轮 rerun 或 M3。
17. 后续 Stage 7 repair 仅在本地增加 19 项封闭 public-safe failure phase、唯一固定 reason code、
    exact JSON Schema、全可达阶段 probe 与 cleanup 分类。renderer 不接收异常对象或动态 protected
    值；原 repair Run Contract 的远端效果预算全部为 0，历史根因仍未知。Owner 随后新增
    Stage 7 completion Run Contract，授权受控交付与 serial new first-attempt dispatch；仍禁止
    GitHub rerun，且 Beta PASS 前不得进入 M3。
18. repair 已通过 PR #92–#95 交付并在四个互异 exact-main SHA 各执行一次 workflow attempt 1；
    PR #96 随后绑定完整账本并以新 exact-main SHA 复验。加上历史首次运行，共 6 次
    Alpha/identity cleanup PASS、Beta FAILED、rerun 0。最新固定结果为
    `GITHUB_APP_TOKEN / INSTALLATION_ZERO`，证明现有 App 尚无 installation；T0702/S7AC-002 仍
    `BLOCKED`，Raw/Gmail mutation/M3/Processed/Timeline/schedule 均为 0。
19. 后续受控 repair 修正 GitHub App token response scope，并将单封 404/结构不完整 metadata
    收敛为 typed、bounded quarantine；任何内容泄漏、身份错配、额外 header 或权限/服务错误仍整次
    fail closed。v2 账本区分 1 次 Secret 前 context 拒绝与 11 次 protected first attempt；最终
    exact-main attempt 的 Alpha、Raw-only Beta 与 identity cleanup 全部 PASS，未使用 rerun。
20. 最终公开安全结果只声明 verified within configured budget、Raw remote recovery 100%、
    private namespace 为非零 age ciphertext only，以及 Gmail mutation/M3/Processed/Timeline/
    schedule 为 0。T0702/S7AC-002 已通过，但最终 Acceptance 仍为 0/34、生产仍 BLOCKED、Stage 7
    未完成；当前 Owner 范围明确停在 M3 前。

## 开发入口

1. `python3 machine/tools/validate_package.py`
2. `python3 machine/tools/validate_delivery_status.py`
3. `python3 machine/tools/validate_workflow_matrix.py --governance-root <固定外部检出>`
4. `python3 machine/tools/validate_stage6_secret_scan.py`
5. 通过固定 Governance checkout 运行 `machine/tools/validate_governance.py`

## 当前准确边界

v1.0.6 证明 RMD-06 云执行前置、T0702 protected Raw-only 入口、最小权限契约和真实 PASS：
Alpha/Raw-only Beta/identity cleanup PASS，verified candidate within budget，Raw remote recovery
100%，Gmail mutation/M3/Processed/Timeline/schedule 为 0。公开面不披露精确邮箱计数、private
对象数量或仓标识。该受控 main 交付不是最终发布；T0702/S7AC-002 已通过，但最终 Acceptance、
生产健康与 Stage 7 均未通过。M3 前序已满足，当前 Owner 范围仍明确停在 M3 前。
