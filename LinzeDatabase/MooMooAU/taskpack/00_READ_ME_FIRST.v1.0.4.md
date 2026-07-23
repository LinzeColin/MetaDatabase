# MooMooAU Archive 开发任务包 v1.0.4

- Package ID：`MMAU-ARCHIVE-TP-2026-07-22-V1.0.4`
- 授权依据：v1.0.3 已冻结的 RMD-04 后续顺序与 Owner 的逐 run 推进目标
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：按固定哈希原样继承 v1.0.1；34 RQ、34 AC、58-task DAG 与十条不变量不变
- 直接前序：v1.0.3 Manifest 字节不可变；v1.0.2 控制前序和 v1.0.1 历史基线继续固定
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`LOCAL_ONLY_NOT_PUBLISHED`

## 开发入口

1. 运行 `python3 machine/tools/validate_package.py` 验证 v1.0.4 和三代固定前序；
2. 运行 `python3 machine/tools/validate_delivery_status.py` 读取唯一跨维度状态；
3. 运行 `python3 machine/tools/validate_production_composition.py` 验证 RMD-04 Workflow、源码哈希和
   零外部效果的 contract-only 入口；
4. 运行 `python3 machine/tools/validate_workflow_matrix.py --governance-root <固定外部检出>` 离线回放
   S3–S6 累计入口和历史负向控制；
5. 运行 `python3 machine/tools/validate_evidence.py evidence/tasks`，并通过固定 Governance checkout
   运行 `validate_governance.py`；
6. 每次 run 最多处理一个 Stage 或复审修复 task group；完成全部修复和最终复审后才一次上传 GitHub。

## RMD-04 已完成边界

- `.github/workflows/moomooau-production.yml` 仍由 `MOOMOOAU_PRODUCTION_ENABLED == 'true'` 和受保护
  Environment 双重关闭，但在获得后续授权时只会调用唯一 `production` composition；
- composition 在任何凭据交换前验证 GA 前序、24 小时内容量快照、Active sender/classification/parser
  registries、age recipient/identity 和 GitHub App key；
- 加密远程 Gmail checkpoint v2 保存最后成功 Sydney 日期，为漏跑补偿提供跨 run 水位；v1 只读兼容；
- 正式适配器已绑定 Gmail、单一 private Repository、Raw/Processed、远程恢复、exact message Trash、
  私有 Timeline snapshot 和单一加密 live Asset；首次导入时间从已恢复 Processed lineage 读取；
- 合成 HTTP 端到端证明 1 条 verified message 在远程恢复后才 Trash，且 Timeline 最大/最终均为 1；
- 以上仅为本地合成机制证据：真实 Gmail、私有仓、Secret、受保护 Oracle、生产 Workflow 和远端发布
  均为 0/NOT_RUN，`production_health_claimed=false`。

当前准确状态：evidence 58/58；本地机制证据 58/58；正式任务 7/58；受保护 Oracle 0/43；最终验收
0/34；生产运行 0；未发布。下一 run 只允许处理 RMD-05 assurance provenance，不得顺带执行受保护验收、
生产运行或上传。

## 冻结边界

v1.0.1 的全部安全边界继续有效：只处理确定性双重验证的 Moomoo AU 入站消息；只允许 exact message
Trash；远端恢复成功前禁止 M3；恰好一个私有数据仓；Raw 与敏感 Processed 持久化前 age 加密；Timeline
健康稳态恰好一个且任何时刻最多一个；真实邮件、附件、密码、Token 与私钥永不进入模型上下文；本地电脑
和自建服务器零生产持久化。
