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
