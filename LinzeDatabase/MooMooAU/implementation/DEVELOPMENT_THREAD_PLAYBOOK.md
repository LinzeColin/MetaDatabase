# Codex 开发线程执行手册

## 第一条动作

```bash
python3 machine/tools/validate_package.py
python3 machine/tools/validate_stage0.py --governance-root <固定版本的外部检出目录> --require-pass
```

若失败，先修任务包导入问题，不开始实现。

## 阅读顺序

1. `taskpack/00_READ_ME_FIRST.v1.0.1.md`；
2. `machine/facts/canonical_facts.json`；
3. `machine/contracts/requirements.json`；
4. `machine/contracts/acceptance_contract.json` 与 `stage_acceptance_contract.json`；
5. `machine/contracts/task_graph.json`；
6. `machine/contracts/traceability_matrix.csv`；
7. 双平面七文件、PRD、架构、安全、测试和发布文档。

## 开发规则

- 按 DAG 中第一个 `planned` 且依赖全部通过的 Task 工作；
- 每次开发运行最多完成一个 Stage；Stage 内可以本地提交，但 S0–S7、最终复审和修复全部完成前不得上传 GitHub；
- 先写/更新测试和 Oracle，再实现；
- 所有成功结论必须引用测试和 Evidence 路径；
- 不在 PR 中请求真实邮件、Secret、账号或私钥；
- 不在未通过 Gate 时访问真实 Gmail 或启用 M3；
- 不改变冻结不变量，除非用户明确授权新版本；
- 普通可逆工程选择按默认值推进，不向用户抛出实现细节问题。

## Stop Condition 输出格式

仅在以下情况暂停：不可逆风险、范围外权限、Acceptance Oracle 不可执行、公开泄漏、真实数据需要进入模型、用户必须亲自完成 OAuth/下载 Recovery Key。

暂停时只输出：

```text
最小决策问题：
证据：
默认建议：
不决策后果：
可继续的非阻塞任务：
```

## Stage 完成定义

- Task 输出存在；
- 当前 Stage 的局部验收测试通过；关联最终 Acceptance 保留追踪，并在所属实现阶段与最终复审中强制通过；
- Evidence JSON Schema 有效；
- Traceability 更新；
- 无真实敏感数据；
- 回滚可执行；
- 双平面无漂移；
- 当前 Stage 的全部本地门禁全绿；未运行的后续 Stage 不得报告为通过。

## 用户常用语义

- “立即同步 Moomoo”：开发线程触发受保护 `workflow_dispatch`；
- “查看 Moomoo 状态”：读取公开脱敏 health evidence；
- “显示最新时间线”：触发受保护临时解密展示，不保存本地/Artifact；
- “修复 Moomoo 失败”：定位公开错误码、修改公开代码、补测试、PR；
- “暂停/恢复”：修改 Feature Flag，不删除 Raw。

## 最终不变量

- 仅处理经确定性双重验证的 Moomoo AU 相关入站消息；其他邮件零读取正文、零下载、零修改。
- M3 适用于所有已验证 Moomoo 相关入站邮件类型；只调用 users.messages.trash，永久 delete 与 thread trash 永久禁用。
- 公开代码仓固定为 LinzeColin/MetaDatabase/LinzeDatabase/MooMooAU；只有一个由受保护 immutable Repository ID 定位的私有数据仓，名称不进入公开树。
- 用户电脑与自建服务器不运行、不持久化；生产仅使用 GitHub-hosted/Codex cloud 临时环境。
- 全部 Raw 和敏感 Processed 均 age 加密；公开面只允许脱敏 Inventory、Schema、Evidence。
- 每日 Australia/Sydney 04:30 运行；周日同一运行执行 Full Reconciliation。
- Timeline 健康稳态恰好一个、任何时刻最多一个加密最新资产：moomooau-live/timeline-latest.png.age；失败可短暂为零并确定性修复。
- Codex 开发线程是用户唯一交互入口；Codex Automation 只做普通被动健康检查，非控制平面关键路径。
- 真实邮件、附件、PDF 密码和 age 私钥永不传给模型。
- H2 Moomoo Portal、券商交易 API、下单、Sent/Drafts 均不在范围内。
