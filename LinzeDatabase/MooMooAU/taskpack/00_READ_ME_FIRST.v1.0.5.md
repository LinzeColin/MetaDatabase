# MooMooAU Archive 开发任务包 v1.0.5

- Package ID：`MMAU-ARCHIVE-TP-2026-07-22-V1.0.5`
- 授权依据：v1.0.4 已冻结的 RMD-05 后续顺序与 Owner 的逐 run 推进目标
- 目标代码位置：`LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU`
- 产品契约：按固定哈希原样继承 v1.0.1；34 RQ、34 AC、58-task DAG 与十条不变量不变
- 直接前序：v1.0.4 Manifest 字节不可变；v1.0.3、v1.0.2 与 v1.0.1 前序继续固定
- 唯一当前状态：`machine/status/latest.json`
- 发布状态：`LOCAL_ONLY_NOT_PUBLISHED`

## 开发入口

1. 运行 `python3 machine/tools/validate_package.py` 验证 v1.0.5 与四代固定前序；
2. 运行 `python3 machine/tools/validate_delivery_status.py` 读取唯一跨维度状态；
3. 运行 `python3 machine/tools/validate_assurance_reviews.py` 验证 clean Git 上的 18-attempt 双模型来源链；
4. 运行 `python3 machine/stages/S6/tools/validate_stage6.py --governance-root <固定外部检出> --cumulative-final`
   验证 receipt-bound Stage 6 v2；
5. 运行 `python3 machine/tools/validate_stage6_secret_scan.py`，并通过固定 Governance checkout 运行
   `validate_governance.py`；
6. 每次 run 最多处理一个 Stage 或复审修复 task group；完成全部修复和最终复审后才一次上传 GitHub。

## RMD-05 已完成边界

- 执行候选 `dc8f7be36f45d3368cb2a6931fdb6cdcdf1fefc1` 与 review anchor
  `2ba0d34cee89672297d7c575205c3d4bf854461b` 共享 tree
  `673132302ed909d8c02e856fdb19887b20c3f447`；anchor 只以两个固定 trailer 绑定候选与 receipt；
- `execution-receipt17.json` 绑定 19 个唯一、零退出的本地 gate command；回执不保留 raw logs，所有摘要脱敏；
- 两个模型家族各有 18 次有序复审、共 36 个互异平台 task ID；全部 adverse/rejected/superseded
  记录保留，最终两份 PASS 回复关闭完整 finding 历史；
- Stage 6 v2、Acceptance、状态、治理 facts/七文档与 package authority 均由已审候选和冻结参数确定性生成；
- RMD-05 只关闭 assurance provenance：真实 Gmail、私有仓、Secret、受保护 Oracle、生产 Workflow、
  部署与发布均为 0/NOT_RUN，最终 Acceptance 仍为 0/34。

当前准确状态：evidence 58/58；本地机制证据 58/58；正式任务 7/58；受保护 Oracle 0/43；最终验收
0/34；生产运行 0；未发布。下一 run 只允许处理 RMD-06 protected acceptance and observation，不得顺带
执行 RMD-07、生产、部署或上传。

## 冻结边界

v1.0.1 的全部安全边界继续有效：只处理确定性双重验证的 Moomoo AU 入站消息；只允许 exact message
Trash；远端恢复成功前禁止 M3；恰好一个私有数据仓；Raw 与敏感 Processed 持久化前 age 加密；Timeline
健康稳态恰好一个且任何时刻最多一个；真实邮件、附件、密码、Token 与私钥永不进入模型上下文；本地电脑
和自建服务器零生产持久化。
