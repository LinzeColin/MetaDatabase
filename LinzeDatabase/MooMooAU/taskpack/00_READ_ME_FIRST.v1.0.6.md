# MooMooAU Archive 开发任务包 v1.0.6

- Package ID：`MMAU-ARCHIVE-TP-2026-07-23-V1.0.6`
- 授权依据：Owner 选择方案 2，Governance 保持私有，并为 MetaDatabase 配置单仓只读 Deploy Key
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：原样继承 v1.0.1 的 34 RQ、34 AC、58-task DAG 与十条不变量
- 直接前序：v1.0.5 Manifest 字节不可变；v1.0.4、v1.0.3、v1.0.2 与 v1.0.1 继续固定
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`LOCAL_ONLY_NOT_PUBLISHED`

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

## 开发入口

1. `python3 machine/tools/validate_package.py`
2. `python3 machine/tools/validate_delivery_status.py`
3. `python3 machine/tools/validate_workflow_matrix.py --governance-root <固定外部检出>`
4. `python3 machine/tools/validate_stage6_secret_scan.py`
5. 通过固定 Governance checkout 运行 `machine/tools/validate_governance.py`

## 当前准确边界

v1.0.6 只证明 RMD-06 云执行前置代码与最小权限依赖认证契约已就绪。受保护 Oracle、真实 Gmail、
唯一私有数据仓、生产 Workflow、部署、最终 Acceptance 与最终发布仍为 `0` 或 `NOT_RUN`。
受控候选分支若用于 GitHub-hosted RMD-06 预检，只是远端验证输入，不等于最终发布；任何失败或未知结果
立即停止，不得读取生产 Secret 或扩大权限。
